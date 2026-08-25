"""
Mini-simulateur cinématique 2D — un substitut léger de CARLA, sans GPU.

Il fait avancer ego et agents dans le temps (modèle point-masse), reconstruit à
chaque pas un ScenarioContext via `world.extraction` (le MÊME chemin de code que
la glu CARLA), puis appelle `assess_risk`. On obtient ainsi l'évolution temporelle
du risque — utile pour valider le moteur et produire des figures.

Deux modes :
  - reaction=False : l'ego ne réagit pas (montre comment le risque escalade).
  - reaction=True  : l'ego freine selon le niveau de risque (montre la couche
                     de sécurité — la collision peut être évitée).

Placement initial cohérent avec `carla_world.py` : chaque agent est posé à sa
distance devant l'ego, orienté selon son cap relatif.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import List, Optional

from risk_engine import (
    RiskAssessment, RiskConfig, RiskLevel, ScenarioContext, assess_risk, metrics, modifiers,
)
from risk_engine.control import ObsAgent, commande_recommandee
from risk_engine.geometry import pose_agent_relative
from world.extraction import ActorState, AgentObservation, refresh_context

@dataclass
class Frame:
    t: float
    ego: ActorState
    agents: List[ActorState]
    assessment: RiskAssessment
    ego_accel: float = 0.0   # accélération appliquée à l'ego (< 0 = freinage)
    collision: bool = False  # vrai si un agent est en contact avec l'ego à cet instant


def _init(ctx: ScenarioContext):
    ego = ActorState(x=0.0, y=0.0, yaw_deg=0.0, speed_ms=ctx.vitesse_ego_kmh / 3.6)
    states, meta, accels = [], [], []
    for ag in ctx.agents:
        # Géométrie déléguée à risk_engine/geometry.py : le moteur (PET 2D) et
        # le simulateur doivent placer les agents exactement de la même façon.
        x0, y0, yaw = pose_agent_relative(
            ag.distance_m, ag.ecart_lateral_m, ag.cap_relatif_deg)
        states.append(ActorState(x=x0, y=y0, yaw_deg=yaw, speed_ms=ag.vitesse_kmh / 3.6))
        meta.append((ag.type_agent, ag.profondeur_mesuree))
        accels.append(ag.acceleration_ms2)
    return ego, states, meta, accels


def _advance(s: ActorState, accel: float, dt: float) -> ActorState:
    v = max(0.0, s.speed_ms + accel * dt)
    r = math.radians(s.yaw_deg)
    return replace(s, x=s.x + v * math.cos(r) * dt, y=s.y + v * math.sin(r) * dt, speed_ms=v)


def run(
    ctx: ScenarioContext,
    dt: float = 0.1,
    t_max: float = 12.0,
    reaction: bool = False,
    cfg: Optional[RiskConfig] = None,
    collision_m: float = 1.5,
) -> List[Frame]:
    cfg = cfg or RiskConfig()
    ego, states, meta, accels = _init(ctx)
    frames: List[Frame] = []
    t = 0.0
    while t <= t_max + 1e-9:
        observations = [AgentObservation(states[i], meta[i][0], meta[i][1]) for i in range(len(states))]
        ctx_t = refresh_context(ctx, ego, observations)
        a = assess_risk(ctx_t, cfg)

        # Freinage : logique déléguée au moteur (`risk_engine/control.py`), le
        # même code sera utilisé côté CARLA — pas de duplication.
        if not reaction:
            ego_accel = 0.0
        else:
            obs = [ObsAgent(x=s.x, y=s.y, drac=ar.drac)
                   for s, ar in zip(states, a.details)]
            cmd = commande_recommandee(a, ctx_t, ego.x, ego.y, obs)
            ego_accel = cmd.acceleration_ms2

        # Détection de collision à cet instant (fix B) : contact avec un agent.
        est_collision = any(math.hypot(s.x - ego.x, s.y - ego.y) < collision_m for s in states)
        frames.append(Frame(round(t, 3), ego, list(states), a, ego_accel, est_collision))
        if est_collision:
            break  # l'ego s'arrête à l'impact plutôt que de traverser l'agent

        ego = _advance(ego, ego_accel, dt)
        states = [_advance(states[i], accels[i], dt) for i in range(len(states))]
        t += dt
    return frames


def collision(frames: List[Frame], collision_m: float = 1.5) -> bool:
    return any(f.collision for f in frames)


def diagnostic_collision(frames: List[Frame], ctx: ScenarioContext,
                         collision_m: float = 1.5) -> str:
    """Indique si une éventuelle collision était physiquement évitable côté ego.

    Trois cas :
    - Pas de collision : rien à diagnostiquer.
    - L'ego est à l'arrêt à l'impact : la collision provient d'un autre agent
      (l'ego ne pouvait plus rien faire par le freinage). Hors de sa responsabilité.
    - L'ego roulait encore : on compare la décélération requise initiale à
      l'adhérence disponible µ·g pour dire si un meilleur pilotage aurait évité
      la collision (ÉVITABLE) ou si elle dépassait les capacités physiques
      du véhicule (INÉVITABLE).
    """
    if not collision(frames, collision_m):
        return "pas de collision"

    dernier = frames[-1]

    # Cas 1 : l'ego est à l'arrêt à l'impact — il ne pouvait plus freiner davantage.
    # La collision provient d'un autre agent, hors de la responsabilité de l'ego.
    if dernier.ego.speed_ms < 0.1:  # tolérance ~ 0,36 km/h
        return ("collision SUBIE : l'ego était à l'arrêt à l'impact "
                "(un autre agent l'a percuté, hors de sa responsabilité)")

    # Cas 2 : l'ego roulait encore — on peut évaluer si le freinage disponible
    # aurait suffi.
    a_max = modifiers.mu(ctx.etat_route) * metrics.G
    idx = [i for i, s in enumerate(dernier.agents)
           if math.hypot(s.x - dernier.ego.x, s.y - dernier.ego.y) < collision_m]
    requis = max((frames[0].assessment.details[i].drac for i in idx), default=0.0)
    if requis > a_max:
        return (f"collision INÉVITABLE : freinage requis {requis:.1f} m/s² "
                f"> adhérence disponible {a_max:.1f} m/s² (l'ego a freiné au maximum)")
    return (f"collision ÉVITABLE (requis {requis:.1f} <= {a_max:.1f} m/s²) "
            f"— à investiguer")