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
from world.extraction import ActorState, AgentObservation, refresh_context

# Décélérations VISÉES par l'ego selon le niveau (mode réactif), en m/s².
# Elles sont ensuite PLAFONNÉES à l'adhérence disponible µ·g (voir run) : sur sol
# glissant, l'ego ne peut pas freiner aussi fort, même s'il le « veut ».
FREINAGE = {
    RiskLevel.SAFE: 0.0,
    RiskLevel.WATCH: -2.0,
    RiskLevel.DANGER: -5.0,
    RiskLevel.CRITICAL: -8.0,
}


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
        e = ag.ecart_lateral_m
        if e == 0.0:
            x0, y0, yaw = ag.distance_m, 0.0, ag.cap_relatif_deg
        else:
            # Décalé latéralement : placé à sa distance (droite), orienté de sorte
            # que sa composante longitudinale suive le cap (0 = même sens, 180 =
            # face-à-face) et sa composante latérale ramène vers l'axe (traversée).
            e = max(-ag.distance_m, min(ag.distance_m, e))
            x0 = math.sqrt(max(0.0, ag.distance_m ** 2 - e ** 2))
            y0 = e
            cap = math.radians(ag.cap_relatif_deg)
            yaw = math.degrees(math.atan2(-math.copysign(math.sin(cap), e), math.cos(cap)))
        states.append(ActorState(x=x0, y=y0, yaw_deg=yaw, speed_ms=ag.vitesse_kmh / 3.6))
        meta.append((ag.type_agent, ag.profondeur_mesuree))
        accels.append(ag.acceleration_ms2)
    return ego, states, meta, accels


def _advance(s: ActorState, accel: float, dt: float) -> ActorState:
    v = max(0.0, s.speed_ms + accel * dt)
    r = math.radians(s.yaw_deg)
    return replace(s, x=s.x + v * math.cos(r) * dt, y=s.y + v * math.sin(r) * dt, speed_ms=v)


def _dans_la_voie_devant(s, ego, demi_voie: float = 2.5) -> bool:
    """Vrai si l'agent est devant l'ego et dans sa voie (séparation latérale faible)."""
    return (s.x - ego.x) > 0.2 and abs(s.y - ego.y) < demi_voie


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
    # Décélération maximale réellement atteignable, fixée par l'adhérence (µ·g).
    a_max = modifiers.mu(ctx.etat_route) * metrics.G
    frames: List[Frame] = []
    t = 0.0
    while t <= t_max + 1e-9:
        observations = [AgentObservation(states[i], meta[i][0], meta[i][1]) for i in range(len(states))]
        ctx_t = refresh_context(ctx, ego, observations)
        a = assess_risk(ctx_t, cfg)

        # Freinage fondé sur la PHYSIQUE (fix A) : l'ego freine de la décélération
        # réellement requise par l'agent le plus menaçant DANS SA VOIE (DRAC),
        # plafonnée à l'adhérence µ·g. Robuste au nombre d'agents (on prend le pire).
        # Pour un croisement (agent hors voie), freinage proportionnel au niveau :
        # l'ego ralentit tant que l'agent est dans la voie, puis reprend une fois dégagé.
        if not reaction:
            ego_accel = 0.0
        else:
            # Décélération requise pour s'arrêter QUELQUES MÈTRES AVANT le plus
            # menaçant des agents en voie (marge d'arrêt), plafonnée à µ·g.
            MARGE_ARRET = 6.0
            requis = 0.0
            for ar, s in zip(a.details, states):
                if _dans_la_voie_devant(s, ego) and ar.drac > 0.0:
                    d = math.hypot(s.x - ego.x, s.y - ego.y)
                    d_sur = max(d - MARGE_ARRET, 0.5)
                    requis = max(requis, ar.drac * d / d_sur)  # = v_fermeture² / (2·d_sur)
            if requis > 0.0:
                ego_accel = -min(requis, a_max)
            else:
                ego_accel = max(FREINAGE[a.level], -a_max)

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
    """Indique si une éventuelle collision était physiquement évitable.

    Une collision est INÉVITABLE si, dès le départ, la décélération requise pour
    l'éviter dépassait déjà l'adhérence disponible µ·g (l'ego ne pouvait rien faire
    de plus). Sinon elle est ÉVITABLE et mérite investigation (défaut de pilotage).
    """
    if not collision(frames, collision_m):
        return "pas de collision"
    a_max = modifiers.mu(ctx.etat_route) * metrics.G
    dernier = frames[-1]
    idx = [i for i, s in enumerate(dernier.agents)
           if math.hypot(s.x - dernier.ego.x, s.y - dernier.ego.y) < collision_m]
    requis = max((frames[0].assessment.details[i].drac for i in idx), default=0.0)
    if requis > a_max:
        return (f"collision INÉVITABLE : freinage requis {requis:.1f} m/s² "
                f"> adhérence disponible {a_max:.1f} m/s² (l'ego a freiné au maximum)")
    return (f"collision ÉVITABLE (requis {requis:.1f} <= {a_max:.1f} m/s²) "
            f"— à investiguer")
