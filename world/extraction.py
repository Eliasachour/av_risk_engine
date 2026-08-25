"""
Extraction : transforme l'état brut du monde (poses, vitesses) en ScenarioContext.

C'est la partie GÉOMÉTRIE de l'adaptateur, volontairement séparée de CARLA :
ce sont des maths pures (distances, écarts de cap), donc testables sans lancer
le simulateur. La glu CARLA (`carla_world.py`) ne fait que produire les
`ActorState` à partir des acteurs CARLA puis appeler ces fonctions.

Repère : positions planes (x, y) en mètres, caps (yaw) en degrés, vitesses en m/s.
Le cap relatif suit la convention du tableau de scénarios :
    0°   -> même sens
    90°  -> croisement
    180° -> face-à-face
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import List

from risk_engine.context import Agent, ScenarioContext, TypeAgent


@dataclass
class ActorState:
    """État cinématique brut d'un acteur (ego ou agent), repère monde."""
    x: float
    y: float
    yaw_deg: float
    speed_ms: float


@dataclass
class AgentObservation:
    """Un agent observé : son état + ses métadonnées (type, capteur)."""
    state: ActorState
    type_agent: TypeAgent
    profondeur_mesuree: bool = True
    acceleration_ms2: float = 0.0


def planar_distance(a: ActorState, b: ActorState) -> float:
    """Distance euclidienne plane (m) entre deux acteurs."""
    return math.hypot(b.x - a.x, b.y - a.y)


def relative_heading_deg(ego_yaw_deg: float, agent_yaw_deg: float) -> float:
    """Écart de cap ramené dans [0, 180].
    0 = même sens, 90 = croisement, 180 = face-à-face.
    """
    d = (agent_yaw_deg - ego_yaw_deg + 180.0) % 360.0 - 180.0
    return abs(d)


def ecart_lateral_m(ego: ActorState, autre: ActorState) -> float:
    """Écart latéral signé de `autre` par rapport à l'axe longitudinal de l'ego.

    Positif à droite de l'ego, négatif à gauche. C'est la projection du vecteur
    ego→agent sur la normale au cap de l'ego.

    **Sans cette grandeur, le filtrage latéral du moteur ne peut pas agir.**
    Un agent perçu depuis CARLA arrivait jusqu'ici avec un écart de 0, donc
    considéré comme étant dans la voie de l'ego : voitures garées, véhicules en
    sens inverse et piétons sur le trottoir devenaient tous des conflits
    frontaux. C'était la cause des alertes intempestives en conduite libre.
    """
    dx = autre.x - ego.x
    dy = autre.y - ego.y
    yaw = math.radians(ego.yaw_deg)
    # Normale au cap de l'ego, orientée vers sa droite.
    return -dx * math.sin(yaw) + dy * math.cos(yaw)


def agent_from_observation(ego: ActorState, obs: AgentObservation) -> Agent:
    """Construit un Agent (au sens du moteur) à partir de l'ego et d'une observation."""
    return Agent(
        type_agent=obs.type_agent,
        vitesse_kmh=obs.state.speed_ms * 3.6,
        distance_m=planar_distance(ego, obs.state),
        cap_relatif_deg=relative_heading_deg(ego.yaw_deg, obs.state.yaw_deg),
        acceleration_ms2=obs.acceleration_ms2,
        ecart_lateral_m=ecart_lateral_m(ego, obs.state),
        profondeur_mesuree=obs.profondeur_mesuree,
    )


def refresh_context(
    base: ScenarioContext,
    ego: ActorState,
    observations: List[AgentObservation],
) -> ScenarioContext:
    """Rafraîchit un ScenarioContext avec l'état courant du monde.

    Les champs d'environnement (type de route, météo, état, visibilité…) sont
    repris du contexte de base (ce que l'utilisateur a réglé dans le formulaire) ;
    seuls la vitesse ego et la liste d'agents sont recalculés depuis les poses.
    """
    agents = [agent_from_observation(ego, obs) for obs in observations]
    return replace(base, vitesse_ego_kmh=ego.speed_ms * 3.6, agents=agents)
