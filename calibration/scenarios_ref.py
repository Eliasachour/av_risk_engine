"""
Scénarios de référence SC-01 à SC-06 et leur niveau de risque ATTENDU.

Le niveau attendu est la « vérité terrain » : ce qu'un expert estime être la
bonne classification au vu de la situation. C'est l'étalon contre lequel on
calibre le moteur. Il t'appartient — ajuste librement les `niveau_attendu`
ci-dessous ; tout le reste (paramètres) reprend fidèlement le tableau des
scénarios-types.

Unités : vitesses en km/h, distances en m, accélérations en m/s², caps en degrés
(0 = même sens, 90 = croisement, 180 = face-à-face).
"""
from __future__ import annotations

from dataclasses import dataclass

from risk_engine import (
    Agent,
    EtatRoute,
    Geometrie,
    Heure,
    Meteo,
    RiskLevel,
    ScenarioContext,
    TypeAgent,
    TypeRoute,
)


@dataclass(frozen=True)
class CasReference:
    id: str
    nom: str
    famille: str
    ctx: ScenarioContext
    niveau_attendu: RiskLevel


# --- Fabriques compactes : composer un scénario tient en une ligne ------------
def _ag(type_agent, v, d, cap, a=0.0, ecart=0.0, mesuree=True):
    return Agent(type_agent, vitesse_kmh=v, distance_m=d, cap_relatif_deg=cap,
                 acceleration_ms2=a, ecart_lateral_m=ecart, profondeur_mesuree=mesuree)


def _ctx(ego, agents, route=TypeRoute.NATIONALE, geo=Geometrie.DROITE, limite=90,
         travaux=False, etat=EtatRoute.SEC, meteo=Meteo.CLAIR, heure=Heure.JOUR, vis=500):
    return ScenarioContext(
        vitesse_ego_kmh=ego, type_route=route, geometrie=geo, limite_vitesse_kmh=limite,
        zone_travaux=travaux, etat_route=etat, meteo=meteo, heure=heure,
        visibilite_m=vis, agents=agents)


# --- SC-01 : approche frontale (face-à-face), véhicule lointain --------------
_sc01 = ScenarioContext(
    vitesse_ego_kmh=90,
    type_route=TypeRoute.NATIONALE, geometrie=Geometrie.DROITE,
    limite_vitesse_kmh=90, zone_travaux=False,
    etat_route=EtatRoute.SEC, meteo=Meteo.CLAIR, heure=Heure.JOUR, visibilite_m=500,
    agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=90, distance_m=500,
                  cap_relatif_deg=180, acceleration_ms2=0.0)],
)

# --- SC-02 : freinage brusque du véhicule de tête (suivi longitudinal) -------
_sc02 = ScenarioContext(
    vitesse_ego_kmh=90,
    type_route=TypeRoute.NATIONALE, geometrie=Geometrie.DROITE,
    limite_vitesse_kmh=90, zone_travaux=False,
    etat_route=EtatRoute.SEC, meteo=Meteo.CLAIR, heure=Heure.JOUR, visibilite_m=500,
    agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=0, distance_m=40,
                  cap_relatif_deg=0, acceleration_ms2=-8.0)],
)

# --- SC-03 : piéton traversant (croisement) ----------------------------------
_sc03 = ScenarioContext(
    vitesse_ego_kmh=50,
    type_route=TypeRoute.URBAIN, geometrie=Geometrie.DROITE,
    limite_vitesse_kmh=50, zone_travaux=False,
    etat_route=EtatRoute.SEC, meteo=Meteo.CLAIR, heure=Heure.JOUR, visibilite_m=500,
    agents=[Agent(TypeAgent.PIETON, vitesse_kmh=5, distance_m=30,
                  cap_relatif_deg=90, acceleration_ms2=0.0)],
)

# --- SC-04 : zone de travaux, ouvrier proche (quasi-longitudinal) ------------
_sc04 = ScenarioContext(
    vitesse_ego_kmh=50,
    type_route=TypeRoute.NATIONALE, geometrie=Geometrie.DROITE,
    limite_vitesse_kmh=30, zone_travaux=True,
    etat_route=EtatRoute.SEC, meteo=Meteo.CLAIR, heure=Heure.JOUR, visibilite_m=200,
    agents=[Agent(TypeAgent.OUVRIER, vitesse_kmh=3, distance_m=20,
                  cap_relatif_deg=15, acceleration_ms2=0.0)],
)

# --- SC-05 : virage serré + obstacle caché (face-à-face), visibilité dégradée -
_sc05 = ScenarioContext(
    vitesse_ego_kmh=50,
    type_route=TypeRoute.DEPARTEMENTALE, geometrie=Geometrie.VIRAGE,
    limite_vitesse_kmh=50, zone_travaux=False,
    etat_route=EtatRoute.SEC, meteo=Meteo.CLAIR, heure=Heure.JOUR, visibilite_m=60,
    agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=30, distance_m=50,
                  cap_relatif_deg=160, acceleration_ms2=0.0)],
)

# --- SC-06 : multi-agents (voiture en sens inverse + cycliste traversant) -----
_sc06 = ScenarioContext(
    vitesse_ego_kmh=85,
    type_route=TypeRoute.AUTOROUTE, geometrie=Geometrie.DROITE,
    limite_vitesse_kmh=90, zone_travaux=False,
    etat_route=EtatRoute.SEC, meteo=Meteo.CLAIR, heure=Heure.JOUR, visibilite_m=500,
    agents=[
        Agent(TypeAgent.VOITURE, vitesse_kmh=120, distance_m=200,
              cap_relatif_deg=180, acceleration_ms2=2.0),
        Agent(TypeAgent.CYCLISTE, vitesse_kmh=15, distance_m=25,
              cap_relatif_deg=45, acceleration_ms2=0.0),
    ],
)


# >>> NIVEAUX ATTENDUS — vérité terrain, à ajuster librement <<<
REFERENCES = [
    CasReference("SC-01", "Approche frontale", "Face-à-face", _sc01, RiskLevel.SAFE),
    # SC-02 : à 40 m / 90 km/h, l'arrêt exige ~7,8 m/s² < µ·g (~8,8) : évitable par
    # freinage fort -> DANGER (et non CRITICAL/inévitable). Les trois métriques
    # longitudinales (TTC, DRAC, RSS) concordent sur DANGER.
    CasReference("SC-02", "Freinage brusque", "Suivi longitudinal", _sc02, RiskLevel.DANGER),
    # SC-03 : piéton à 30 m, TTC=2,2 s (WATCH). TTC > 2 s : pas de durcissement
    # contextuel selon la règle raffinée (voir ETIQUETAGE.md, étape 3).
    CasReference("SC-03", "Piéton traversant", "Croisement", _sc03, RiskLevel.WATCH),
    # SC-04 : ouvrier (VRU) à 20 m, ego 50 km/h -> TTC=1,5 s (DANGER) + VRU -> CRITICAL.
    CasReference("SC-04", "Zone de travaux", "Quasi-longitudinal", _sc04, RiskLevel.CRITICAL),
    # SC-05 : virage sans visibilité, TTC=2,3 s (WATCH). TTC > 2 s : la visibilité
    # dégradée ne justifie pas un durcissement (règle raffinée, étape 3).
    CasReference("SC-05", "Virage + obstacle caché", "Face-à-face", _sc05, RiskLevel.WATCH),
    CasReference("SC-06", "Multi-agents", "Mixte", _sc06, RiskLevel.CRITICAL),

    # ===== Suivi longitudinal (cap 0) : les 4 niveaux =====
    CasReference("SC-07", "Suivi large", "Suivi",
                 _ctx(90, [_ag(TypeAgent.VOITURE, 85, 120, 0)]), RiskLevel.SAFE),
    # SC-08 : suivi 40 m à 90 km/h, TTC=14 s -> SAFE par la méthode. Note : le RSS
    # (modèle plus conservateur) considère la distance sous la sécurité prouvée ;
    # on retient l'étiquette du TTC, plus proche de la perception humaine.
    CasReference("SC-08", "Suivi à distance moyenne", "Suivi",
                 _ctx(90, [_ag(TypeAgent.VOITURE, 80, 40, 0)]), RiskLevel.SAFE),
    CasReference("SC-09", "Suivi serré à haute vitesse", "Suivi",
                 _ctx(110, [_ag(TypeAgent.VOITURE, 80, 15, 0)], route=TypeRoute.AUTOROUTE, limite=130),
                 RiskLevel.DANGER),
    CasReference("SC-10", "Obstacle immobile proche", "Suivi",
                 _ctx(90, [_ag(TypeAgent.VOITURE, 0, 20, 0)]), RiskLevel.CRITICAL),
    # SC-11 : même géométrie que SC-02 mais sur sol MOUILLÉ : l'arrêt exige ~7,8 m/s²
    # > µ·g mouillé (~6,3) -> devient INÉVITABLE -> CRITICAL (effet des conditions).
    CasReference("SC-11", "Obstacle immobile, chaussée mouillée", "Suivi",
                 _ctx(90, [_ag(TypeAgent.VOITURE, 0, 40, 0)], etat=EtatRoute.MOUILLE, meteo=Meteo.PLUIE, vis=300),
                 RiskLevel.CRITICAL),

    # ===== Croisement / VRU (cap 90, écart latéral) : les 4 niveaux =====
    # SC-12 : piéton à 80 m écart 10 m, TTC=5,8 s (SAFE) ; VRU non confirmé
    # (TTC pas tendu, projeté 2 m à la limite) -> pas de durcissement -> SAFE.
    CasReference("SC-12", "Piéton traversant lointain", "Croisement",
                 _ctx(50, [_ag(TypeAgent.PIETON, 5, 80, 90, ecart=10)], route=TypeRoute.URBAIN, limite=50),
                 RiskLevel.SAFE),
    # SC-13 : piéton à 40 m écart 6 m, TTC=2,9 s (WATCH), projeté ~1,4 m à cet
    # horizon. TTC pas tendu et projeté au bord du seuil : durcissement VRU non
    # confirmé au sens strict -> reste WATCH.
    CasReference("SC-13", "Piéton traversant à mi-distance", "Croisement",
                 _ctx(50, [_ag(TypeAgent.PIETON, 5, 40, 90, ecart=6)], route=TypeRoute.URBAIN, limite=50),
                 RiskLevel.WATCH),
    # SC-14 : piéton à 20 m écart 4 m, TTC=1,4 s (DANGER) + VRU -> CRITICAL.
    CasReference("SC-14", "Piéton traversant proche", "Croisement",
                 _ctx(50, [_ag(TypeAgent.PIETON, 5, 20, 90, ecart=4)], route=TypeRoute.URBAIN, limite=50),
                 RiskLevel.CRITICAL),
    CasReference("SC-15", "Piéton surgissant de nuit", "Croisement",
                 _ctx(50, [_ag(TypeAgent.PIETON, 5, 10, 90, ecart=3, mesuree=False)],
                      route=TypeRoute.URBAIN, limite=50, heure=Heure.NUIT, vis=30), RiskLevel.CRITICAL),
    # SC-16 : cycliste à 20 m écart 5 m, TTC=1,2 s (DANGER) + VRU -> CRITICAL.
    CasReference("SC-16", "Cycliste au carrefour", "Croisement",
                 _ctx(60, [_ag(TypeAgent.CYCLISTE, 15, 20, 90, ecart=5)], route=TypeRoute.URBAIN, limite=50),
                 RiskLevel.CRITICAL),

    # ===== Face-à-face (cap 180) : SAFE / DANGER / CRITICAL =====
    CasReference("SC-17", "Croisement de véhicules lointain", "Face-à-face",
                 _ctx(80, [_ag(TypeAgent.VOITURE, 80, 300, 180)]), RiskLevel.SAFE),
    # SC-18 : face-à-face à 80 m à 140 km/h de fermeture, a_req=9,5 > µg=8,8 sec
    # -> inévitable -> CRITICAL par étape 1 (la visibilité réduite ne fait qu'aggraver).
    CasReference("SC-18", "Face-à-face en virage sans visibilité", "Face-à-face",
                 _ctx(70, [_ag(TypeAgent.VOITURE, 70, 80, 180)], route=TypeRoute.DEPARTEMENTALE,
                      geo=Geometrie.VIRAGE, limite=80, vis=80), RiskLevel.CRITICAL),
    CasReference("SC-19", "Véhicule à contresens proche", "Face-à-face",
                 _ctx(90, [_ag(TypeAgent.VOITURE, 90, 40, 180)]), RiskLevel.CRITICAL),

    # ===== Conditions dégradées (verglas, nuit, brouillard, pluie) =====
    # SC-20 : sur VERGLAS, l'arrêt (~3,8 m/s²) dépasse µ·g (~2,9) -> inévitable -> CRITICAL.
    CasReference("SC-20", "Obstacle immobile sur verglas", "Suivi",
                 _ctx(70, [_ag(TypeAgent.VOITURE, 0, 50, 0)], etat=EtatRoute.VERGLAS, meteo=Meteo.NEIGE,
                      limite=70, vis=200), RiskLevel.CRITICAL),
    # SC-21 : piéton à 25 m écart 5 m de nuit, TTC=1,8 s (DANGER) + VRU/nuit -> CRITICAL.
    CasReference("SC-21", "Piéton de nuit, visibilité réduite", "Croisement",
                 _ctx(50, [_ag(TypeAgent.PIETON, 5, 25, 90, ecart=5, mesuree=False)],
                      route=TypeRoute.URBAIN, limite=50, heure=Heure.NUIT, vis=25), RiskLevel.CRITICAL),
    # SC-22 : face-à-face dans le brouillard, TTC=3,0 s (WATCH). TTC > 2 s : le
    # brouillard ne justifie pas un durcissement (règle raffinée, étape 3).
    CasReference("SC-22", "Face-à-face dans le brouillard", "Face-à-face",
                 _ctx(60, [_ag(TypeAgent.VOITURE, 60, 100, 180)], meteo=Meteo.BROUILLARD, limite=80, vis=40),
                 RiskLevel.WATCH),
    CasReference("SC-23", "Suivi calme sous la pluie", "Suivi",
                 _ctx(50, [_ag(TypeAgent.VOITURE, 50, 80, 0)], etat=EtatRoute.MOUILLE, meteo=Meteo.PLUIE,
                      route=TypeRoute.URBAIN, limite=50, vis=300), RiskLevel.SAFE),
    # SC-24 : ouvrier (VRU) à 12 m en zone de travaux, TTC=1,5 s (DANGER) + VRU -> CRITICAL.
    CasReference("SC-24", "Ouvrier en zone de travaux", "Quasi-longitudinal",
                 _ctx(30, [_ag(TypeAgent.OUVRIER, 3, 12, 45)], limite=30, travaux=True, vis=200),
                 RiskLevel.CRITICAL),
]
