"""
Perception « oracle » — vérité terrain filtrée par distance + champ de vision.

En mode conduite libre, l'ego n'est pas piloté par le moteur mais par un
humain : le moteur ne reçoit donc plus des agents scriptés, mais tout ce qui
grouille dans le monde CARLA (véhicules du Traffic Manager, piétons IA).
Ce module filtre cette foule pour ne remonter au moteur que ce qui est
*dans son champ d'attention* :

- distance ≤ ``rayon_m`` (défaut 60 m — au-delà, plus rien de critique) ;
- angle par rapport au cap de l'ego ≤ ``demi_angle_deg`` (défaut 60° soit un
  cône de 120°, cohérent avec un capteur avant + latéral).

Le mot « oracle » est **assumé** : ce n'est pas une chaîne perception réelle,
c'est la vérité terrain CARLA filtrée. Le HUD le signale explicitement au
conducteur. Passer à une perception par capteurs LiDAR/radar est un chantier
séparé, hors périmètre de ce stage (limite documentée).
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from risk_engine import TypeAgent
from world.extraction import ActorState, AgentObservation

try:
    import carla  # type: ignore
    _HAS_CARLA = True
except ImportError:
    _HAS_CARLA = False


def _carla_disponible() -> bool:
    """Vrai si le module `carla` est importable MAINTENANT.

    La vérification est faite à l'appel, et non figée au moment de l'import :
    un module importé avant que `carla` ne soit disponible resterait sinon
    inutilisable pour toute la durée du processus. C'est notamment le cas quand
    un double de test installe `carla` dans `sys.modules` après coup.
    """
    try:
        import carla  # noqa: F401
        return True
    except ImportError:
        return False


# -----------------------------------------------------------------------------
# Classification blueprint → TypeAgent
# -----------------------------------------------------------------------------

def type_agent_depuis_blueprint(blueprint_id: str) -> Optional[TypeAgent]:
    """Traduit un blueprint CARLA en `TypeAgent` du moteur.

    Retourne ``None`` pour les acteurs qu'on ignore (statiques, sensors, etc.).
    Cette fonction encapsule la connaissance des naming conventions CARLA — si
    un blueprint inconnu apparaît, on préfère le classer en VOITURE (choix
    conservateur : mieux vaut évaluer un risque en trop qu'un risque en moins).
    """
    if blueprint_id.startswith("vehicle."):
        # Camions et gros porteurs
        if any(k in blueprint_id for k in ("firetruck", "carlacola", "sprinter",
                                            "ambulance", "cybertruck")):
            return TypeAgent.CAMION
        # Deux-roues motorisés → traités comme voitures (silhouette proche)
        if any(k in blueprint_id for k in ("harley", "kawasaki", "yamaha",
                                            "vespa", "ninja")):
            return TypeAgent.VOITURE
        # Vélos → cycliste
        if any(k in blueprint_id for k in ("crossbike", "century", "diamondback",
                                            "gazelle")):
            return TypeAgent.CYCLISTE
        return TypeAgent.VOITURE

    if blueprint_id.startswith("walker.pedestrian."):
        # On distingue vaguement les tenues « ouvrier » (id 0002, 0004, 0006)
        try:
            n = int(blueprint_id.rsplit(".", 1)[-1])
            if n in (2, 4, 6, 22):
                return TypeAgent.OUVRIER
        except ValueError:
            pass
        return TypeAgent.PIETON

    return None  # sensor, static, controller…


# -----------------------------------------------------------------------------
# Filtre principal
# -----------------------------------------------------------------------------


def _yaw_de_actor(actor) -> float:
    """Cap de l'acteur en radians (repère monde)."""
    return math.radians(actor.get_transform().rotation.yaw)


def _vitesse_ms(actor) -> float:
    """Norme de la vitesse (m/s)."""
    v = actor.get_velocity()
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def acteurs_percus(
    world,
    ego,
    rayon_m: float = 60.0,
    demi_angle_deg: float = 60.0,
) -> List[Tuple["carla.Actor", TypeAgent, ActorState]]:
    """Retourne la liste des acteurs perçus par l'ego à cet instant.

    Chaque entrée : ``(actor_carla, type_agent, actor_state)`` où
    ``actor_state`` est déjà exprimé en coordonnées monde et prêt à alimenter
    ``AgentObservation`` pour ``refresh_context``.

    Le tri est fait par distance croissante — utile pour couper à N acteurs si
    on veut plafonner la charge du moteur (l'appelant peut faire ``[:N]``).

    Parameters
    ----------
    world : carla.World
    ego : carla.Actor
    rayon_m : float
        Rayon de perception. 60 m = compromis « on voit tout ce qui peut
        devenir critique dans les 3-4 prochaines secondes à 60 km/h ».
    demi_angle_deg : float
        Demi-angle du cône avant. 60° = cône de 120° (vision utile d'un
        capteur avant + un latéral gauche + latéral droit).
    """
    if not _carla_disponible():
        raise RuntimeError("carla n'est pas installé — ce module est CARLA-only.")

    ego_tf = ego.get_transform()
    ego_x, ego_y = ego_tf.location.x, ego_tf.location.y
    ego_yaw = math.radians(ego_tf.rotation.yaw)
    demi_angle_rad = math.radians(demi_angle_deg)

    resultats: List[Tuple["carla.Actor", TypeAgent, ActorState, float]] = []
    for actor in world.get_actors():
        if actor.id == ego.id:
            continue
        type_agent = type_agent_depuis_blueprint(actor.type_id)
        if type_agent is None:
            continue

        loc = actor.get_transform().location
        dx = loc.x - ego_x
        dy = loc.y - ego_y
        d = math.hypot(dx, dy)
        if d > rayon_m or d < 0.5:
            continue

        # Angle du vecteur ego→acteur, ramené dans le repère ego
        angle_relatif = math.atan2(dy, dx) - ego_yaw
        # Normaliser dans [-π, π]
        angle_relatif = math.atan2(math.sin(angle_relatif), math.cos(angle_relatif))
        if abs(angle_relatif) > demi_angle_rad:
            continue

        state = ActorState(
            x=loc.x, y=loc.y,
            yaw_deg=actor.get_transform().rotation.yaw,
            speed_ms=_vitesse_ms(actor),
        )
        resultats.append((actor, type_agent, state, d))

    resultats.sort(key=lambda t: t[3])  # tri par distance croissante
    return [(a, t, s) for a, t, s, _ in resultats]


def contexte_depuis_perception(
    ctx_base,
    ego,
    acteurs_avec_meta: List[Tuple["carla.Actor", TypeAgent, ActorState]],
    carte=None,
    analyses: Optional[dict] = None,
):
    """Reconstruit un `ScenarioContext` à partir de la perception filtrée.

    Deux modes selon que la carte est fournie ou non.

    **Sans carte** (simulateur cinématique, tests) : l'écart latéral est
    euclidien, mesuré perpendiculairement à l'axe instantané de l'ego.
    Correct en ligne droite.

    **Avec carte** (CARLA) : l'écart latéral devient **curviligne**, exprimé en
    nombre de voies le long de la route. C'est indispensable en virage, où
    l'écart euclidien d'un véhicule pourtant situé dans notre propre voie
    grandit avec la courbure — au point de le faire rétrograder en SAFE. Sur un
    rayon de 200 m, un obstacle immobile à 40 m dans notre voie présentait un
    écart euclidien de 4 m et n'était plus détecté.

    Si `analyses` est fourni (dictionnaire indexé par identifiant d'acteur), il
    est rempli au passage avec l'`AnalyseVoie` de chaque véhicule — utile pour
    le HUD et la journalisation, sans refaire le calcul.

    La profondeur est marquée mesurée (vérité terrain), ce qui **surestime les
    capacités réelles d'un système embarqué** — cohérent avec le badge
    « oracle » du HUD.
    """
    from dataclasses import replace as _replace

    from world.extraction import refresh_context

    ego_tf = ego.get_transform()
    ego_state = ActorState(
        x=ego_tf.location.x,
        y=ego_tf.location.y,
        yaw_deg=ego_tf.rotation.yaw,
        speed_ms=_vitesse_ms(ego),
    )
    observations = [
        AgentObservation(state, type_agent, profondeur_mesuree=True)
        for _, type_agent, state in acteurs_avec_meta
    ]
    ctx = refresh_context(ctx_base, ego_state, observations)

    if carte is None:
        return ctx

    # --- Correction curviligne de l'écart latéral --------------------------
    from world.lane_relation import analyser

    agents = list(ctx.agents)
    for i, (acteur, _type, _state) in enumerate(acteurs_avec_meta):
        if i >= len(agents):
            break
        try:
            analyse = analyser(carte, ego_tf, acteur.get_transform())
        except (RuntimeError, AttributeError):
            continue
        if analyses is not None:
            analyses[getattr(acteur, "id", i)] = analyse
        # Position ET cap sont corrigés : sur route courbe, les deux souffrent
        # du même défaut d'extrapolation rectiligne.
        agents[i] = _replace(
            agents[i],
            ecart_lateral_m=analyse.ecart_lateral_m,
            cap_relatif_deg=analyse.cap_relatif_deg,
        )

    return _replace(ctx, agents=agents)
