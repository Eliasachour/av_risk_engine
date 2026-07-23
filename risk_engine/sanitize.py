from __future__ import annotations

import math
from dataclasses import replace
from typing import List, Tuple

from .context import Agent, ScenarioContext

VITESSE_MAX_KMH = 300.0
ACCEL_MIN_MS2, ACCEL_MAX_MS2 = -15.0, 15.0
DISTANCE_MIN_M, DISTANCE_MAX_M = 0.5, 100_000.0
VISIBILITE_MIN_M = 1.0


def _fix(val: float, lo: float, hi: float, defaut: float, label: str, av: List[str]) -> float:
    orig = val
    if val is None or (isinstance(val, (int, float)) and not math.isfinite(val)):
        val = defaut
    new = max(lo, min(hi, val))
    if new != orig:
        av.append(f"{label} : {orig} -> {new}")
    return new


def _fix_cap(cap: float, label: str, av: List[str]) -> float:
    orig = cap
    if cap is None or not math.isfinite(cap):
        cap = 0.0
    cap = cap % 360.0
    if cap > 180.0:
        cap = 360.0 - cap          # repli : le cap est symétrique (cos)
    if cap != orig:
        av.append(f"{label} : {orig} -> {cap}")
    return cap


def sanitize_agent(agent: Agent, idx: int = 1) -> Tuple[Agent, List[str]]:
    av: List[str] = []
    return replace(
        agent,
        vitesse_kmh=_fix(agent.vitesse_kmh, 0.0, VITESSE_MAX_KMH, 0.0, f"agent {idx} vitesse", av),
        distance_m=_fix(agent.distance_m, DISTANCE_MIN_M, DISTANCE_MAX_M, DISTANCE_MIN_M, f"agent {idx} distance", av),
        cap_relatif_deg=_fix_cap(agent.cap_relatif_deg, f"agent {idx} cap", av),
        acceleration_ms2=_fix(agent.acceleration_ms2, ACCEL_MIN_MS2, ACCEL_MAX_MS2, 0.0, f"agent {idx} accélération", av),
        ecart_lateral_m=_fix(agent.ecart_lateral_m, -DISTANCE_MAX_M, DISTANCE_MAX_M, 0.0, f"agent {idx} écart latéral", av),
    ), av


def sanitize_context(ctx: ScenarioContext) -> Tuple[ScenarioContext, List[str]]:
    """Borne les valeurs hors plage physique et renvoie la liste des corrections.

    Aucun rejet : les valeurs trop élevées, NaN/inf ou les caps hors [0, 180] sont
    ramenés dans le domaine admissible, et chaque correction est signalée. Les
    valeurs négatives de distance/vitesse sont, elles, déjà refusées à la
    construction du contexte (échec rapide).
    """
    av: List[str] = []
    ego = _fix(ctx.vitesse_ego_kmh, 0.0, VITESSE_MAX_KMH, 0.0, "vitesse ego", av)
    vis = _fix(ctx.visibilite_m, VISIBILITE_MIN_M, DISTANCE_MAX_M, VISIBILITE_MIN_M, "visibilité", av)
    agents = []
    for i, a in enumerate(ctx.agents, 1):
        na, wa = sanitize_agent(a, i)
        agents.append(na)
        av.extend(wa)
    return replace(ctx, vitesse_ego_kmh=ego, visibilite_m=vis, agents=agents), av
