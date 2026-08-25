"""
Contrôle de la météo en direct, depuis le HUD.

Deux niveaux :

- **Préréglages** — les touches F1 à F6 basculent instantanément entre des
  ambiances complètes (clair, couvert, pluie, orage, brouillard, nuit).
- **Réglages fins** — les touches I/K, O/L, P/M et N/B ajustent respectivement
  nuages, précipitations, brouillard et hauteur du soleil.

Point important : la météo CARLA est **visuelle**. Elle n'agit pas sur
l'adhérence des pneus. Pour que le moteur de risque voie la dégradation, ce
module met aussi à jour le `ScenarioContext` (état de route, visibilité), qui
est ce que le moteur consomme réellement. Les deux restent donc cohérents —
ce que le conducteur voit correspond à ce que le moteur évalue.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

try:
    import pygame  # type: ignore
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False

from risk_engine.context import EtatRoute, Heure, Meteo


# ---------------------------------------------------------------------------
# Préréglages
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PresetMeteo:
    """Une ambiance complète : visuel CARLA + état vu par le moteur."""
    nom: str
    # Champs carla.WeatherParameters
    cloudiness: float
    precipitation: float
    precipitation_deposits: float
    wind_intensity: float
    fog_density: float
    fog_distance: float
    wetness: float
    sun_altitude_angle: float
    # Ce que le MOTEUR doit en déduire
    meteo: Meteo
    etat_route: EtatRoute
    heure: Heure
    visibilite_m: float


#: Préréglages accessibles par F1..F7, dans cet ordre.
#: Les enums du moteur ne connaissent que CLAIR / PLUIE / BROUILLARD / NEIGE
#: et SEC / MOUILLE / NEIGEUX / VERGLAS — les préréglages s'y conforment.
PRESETS: Tuple[PresetMeteo, ...] = (
    PresetMeteo("Clair", 10, 0, 0, 10, 0, 0, 0, 65,
                Meteo.CLAIR, EtatRoute.SEC, Heure.JOUR, 800),
    PresetMeteo("Couvert", 75, 0, 0, 20, 0, 0, 5, 40,
                Meteo.CLAIR, EtatRoute.SEC, Heure.JOUR, 500),
    PresetMeteo("Pluie", 85, 70, 60, 40, 8, 60, 60, 35,
                Meteo.PLUIE, EtatRoute.MOUILLE, Heure.JOUR, 250),
    PresetMeteo("Orage", 95, 100, 90, 80, 15, 40, 90, 20,
                Meteo.PLUIE, EtatRoute.MOUILLE, Heure.JOUR, 120),
    PresetMeteo("Brouillard", 60, 0, 0, 10, 85, 25, 10, 45,
                Meteo.BROUILLARD, EtatRoute.SEC, Heure.JOUR, 60),
    # Neige : le cas le plus sévère pour le moteur (mu.g tombe à ~2,9 m/s2),
    # celui qui déclenche la correction RSS de la décision D14.
    PresetMeteo("Neige / verglas", 90, 80, 85, 30, 20, 50, 70, 30,
                Meteo.NEIGE, EtatRoute.VERGLAS, Heure.JOUR, 150),
    PresetMeteo("Nuit claire", 15, 0, 0, 10, 0, 0, 0, -25,
                Meteo.CLAIR, EtatRoute.SEC, Heure.NUIT, 150),
)


# Touches F1..F6 -> index de preset
_TOUCHES_PRESET: Dict[int, int] = {}
if _HAS_PYGAME:
    _TOUCHES_PRESET = {
        pygame.K_F1: 0, pygame.K_F2: 1, pygame.K_F3: 2,
        pygame.K_F4: 3, pygame.K_F5: 4, pygame.K_F6: 5,
        pygame.K_F7: 6,
    }


# ---------------------------------------------------------------------------
# Contrôleur
# ---------------------------------------------------------------------------


class ControleMeteo:
    """Gère la météo courante et son application au monde CARLA.

    Utilisation dans la boucle principale :

        meteo = ControleMeteo(pont.world, ctx_base)
        ...
        for event in pygame.event.get():        # ou via hud.evenements_bruts()
            meteo.gerer_touche(event)
        ctx_base = meteo.contexte()             # contexte à jour pour le moteur
    """

    #: Pas d'ajustement par appui pour les réglages fins.
    PAS = 8.0

    def __init__(self, world, ctx_base):
        self.world = world
        self._ctx_base = ctx_base
        self._preset_index = 0
        self._nom = PRESETS[0].nom
        # Copie mutable des champs visuels
        p = PRESETS[0]
        self._visuel = dict(
            cloudiness=p.cloudiness,
            precipitation=p.precipitation,
            precipitation_deposits=p.precipitation_deposits,
            wind_intensity=p.wind_intensity,
            fog_density=p.fog_density,
            fog_distance=p.fog_distance,
            wetness=p.wetness,
            sun_azimuth_angle=0.0,
            sun_altitude_angle=p.sun_altitude_angle,
        )
        self._moteur = dict(
            meteo=p.meteo, etat_route=p.etat_route,
            heure=p.heure, visibilite_m=p.visibilite_m,
        )
        self._dirty = True
        # Friction : on retient la valeur d'origine pour raisonner en ratio.
        self._friction_defaut = None
        self._ratio_friction_applique = 1.0

    # -------------------------------------------------- application

    def appliquer_si_besoin(self) -> None:
        """Pousse la météo vers CARLA seulement si elle a changé."""
        if not self._dirty:
            return
        import carla
        self.world.set_weather(carla.WeatherParameters(**self._visuel))
        self._dirty = False

    def appliquer_preset_initial(self, meteo: Meteo, heure: Heure) -> None:
        """Aligne le préréglage de départ sur ce que l'utilisateur a choisi."""
        for i, p in enumerate(PRESETS):
            if p.meteo == meteo and p.heure == heure:
                self._charger_preset(i)
                return
        # Rien d'exact : au moins respecter le jour/nuit
        self._charger_preset(5 if heure == Heure.NUIT else 0)

    # -------------------------------------------------- entrées clavier

    def gerer_touche(self, event) -> bool:
        """Traite un événement KEYDOWN. Renvoie True si la météo a changé."""
        if event.type != pygame.KEYDOWN:
            return False

        # Préréglages F1..F6
        if event.key in _TOUCHES_PRESET:
            self._charger_preset(_TOUCHES_PRESET[event.key])
            return True

        # Réglages fins
        ajustements = {
            pygame.K_i: ("cloudiness", +self.PAS),
            pygame.K_k: ("cloudiness", -self.PAS),
            pygame.K_o: ("precipitation", +self.PAS),
            pygame.K_l: ("precipitation", -self.PAS),
            pygame.K_p: ("fog_density", +self.PAS),
            pygame.K_m: ("fog_density", -self.PAS),
            pygame.K_n: ("sun_altitude_angle", +self.PAS),
            pygame.K_b: ("sun_altitude_angle", -self.PAS),
        }
        if event.key in ajustements:
            champ, delta = ajustements[event.key]
            borne_basse = -90.0 if champ == "sun_altitude_angle" else 0.0
            borne_haute = 90.0 if champ == "sun_altitude_angle" else 100.0
            self._visuel[champ] = max(borne_basse,
                                      min(borne_haute, self._visuel[champ] + delta))
            # Les dépôts au sol et l'humidité suivent la pluie
            if champ == "precipitation":
                self._visuel["precipitation_deposits"] = self._visuel["precipitation"] * 0.85
                self._visuel["wetness"] = self._visuel["precipitation"] * 0.85
            if champ == "fog_density" and self._visuel["fog_density"] > 0:
                self._visuel["fog_distance"] = max(5.0, 120.0 - self._visuel["fog_density"])
            self._nom = "Personnalise"
            self._synchroniser_moteur()
            self._dirty = True
            return True

        return False

    # -------------------------------------------------- état

    def contexte(self):
        """Renvoie le ScenarioContext de base mis à jour (météo, route, heure)."""
        return replace(self._ctx_base, **self._moteur)

    def nom(self) -> str:
        return self._nom

    def resume(self) -> str:
        """Ligne courte pour le HUD."""
        v = self._visuel
        return (f"{self._nom}  nuages {v['cloudiness']:.0f}  "
                f"pluie {v['precipitation']:.0f}  "
                f"brouillard {v['fog_density']:.0f}  "
                f"soleil {v['sun_altitude_angle']:+.0f}deg")

    # -------------------------------------------------- interne

    def _charger_preset(self, index: int) -> None:
        index = max(0, min(len(PRESETS) - 1, index))
        p = PRESETS[index]
        self._preset_index = index
        self._nom = p.nom
        self._visuel.update(
            cloudiness=p.cloudiness,
            precipitation=p.precipitation,
            precipitation_deposits=p.precipitation_deposits,
            wind_intensity=p.wind_intensity,
            fog_density=p.fog_density,
            fog_distance=p.fog_distance,
            wetness=p.wetness,
            sun_altitude_angle=p.sun_altitude_angle,
        )
        self._moteur.update(
            meteo=p.meteo, etat_route=p.etat_route,
            heure=p.heure, visibilite_m=p.visibilite_m,
        )
        self._dirty = True

    def _synchroniser_moteur(self) -> None:
        """Déduit l'état vu par le moteur à partir des réglages visuels.

        C'est le point délicat : le moteur raisonne sur des catégories
        (sec / mouillé / neigeux / verglas) alors que CARLA manipule des
        pourcentages. On applique des seuils explicites plutôt que de laisser
        les deux divergences s'installer.
        """
        v = self._visuel

        # Météo dominante. On ne devine PAS la neige depuis les réglages fins
        # (rien ne la distingue de la pluie côté CARLA) : elle ne s'obtient que
        # par le préréglage F6, qui la pose explicitement.
        if v["fog_density"] >= 40:
            self._moteur["meteo"] = Meteo.BROUILLARD
        elif v["precipitation"] >= 30:
            self._moteur["meteo"] = Meteo.PLUIE
        else:
            self._moteur["meteo"] = Meteo.CLAIR

        # État de la chaussée : piloté par les dépôts au sol
        depots = v["precipitation_deposits"]
        if depots >= 30:
            self._moteur["etat_route"] = EtatRoute.MOUILLE
        else:
            self._moteur["etat_route"] = EtatRoute.SEC

        # Jour / nuit
        self._moteur["heure"] = (Heure.NUIT if v["sun_altitude_angle"] < 0
                                 else Heure.JOUR)

        # Visibilité : brouillard puis pluie, sinon dégagé
        if v["fog_density"] > 0:
            vis = max(20.0, 400.0 - 4.0 * v["fog_density"])
        elif v["precipitation"] > 0:
            vis = max(80.0, 600.0 - 4.0 * v["precipitation"])
        else:
            vis = 800.0
        if self._moteur["heure"] == Heure.NUIT:
            vis *= 0.4
        self._moteur["visibilite_m"] = round(vis)

    # -------------------------------------------------- friction des pneus

    def appliquer_friction(self, vehicule) -> Optional[float]:
        """Aligne l'adhérence SIMULÉE sur l'état de route vu par le moteur.

        Sans cela, la météo CARLA reste purement visuelle : sur « verglas »,
        le véhicule freinerait encore comme sur sol sec alors que le moteur
        suppose µ·g ≈ 2,9 m/s². Le simulé et l'évalué divergeraient — un
        défaut de cohérence physique difficile à défendre.

        **Limite assumée.** ``tire_friction`` de CARLA n'est pas le µ physique :
        c'est un scalaire de friction Unreal (~3,5 par défaut). On ne peut donc
        pas y injecter µ directement. On applique un rapport : la friction
        devient ``friction_defaut × (µ_cible / µ_sec)``. L'ordre de grandeur et
        la hiérarchie entre états sont respectés, la valeur absolue est une
        approximation — c'est documenté comme telle.

        Renvoie le ratio appliqué, ou None si l'opération a échoué.
        """
        from risk_engine import modifiers

        mu_cible = modifiers.mu(self._moteur["etat_route"])
        mu_sec = modifiers.mu(EtatRoute.SEC)
        ratio = mu_cible / mu_sec if mu_sec > 0 else 1.0

        if abs(ratio - self._ratio_friction_applique) < 0.01:
            return self._ratio_friction_applique  # déjà à jour

        try:
            physique = vehicule.get_physics_control()
            roues = []
            for roue in physique.wheels:
                if self._friction_defaut is None:
                    self._friction_defaut = roue.tire_friction
                roue.tire_friction = self._friction_defaut * ratio
                roues.append(roue)
            physique.wheels = roues
            vehicule.apply_physics_control(physique)
            self._ratio_friction_applique = ratio
            return ratio
        except (RuntimeError, AttributeError):
            return None
