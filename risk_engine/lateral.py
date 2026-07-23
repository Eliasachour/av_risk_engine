"""
Filtrage latéral 2D — atténue la menace d'un agent qui n'est pas sur la trajectoire
de collision de l'ego.

Idée : autour de l'axe longitudinal de l'ego, on définit un CORRIDOR DE MENACE :
  - dans le corridor central (~1,5 m de part et d'autre) : menace pleine (facteur 1),
  - jusqu'à environ deux fois la largeur d'une voie (~3,5 m) : atténuation linéaire,
  - au-delà : pas de menace directe (facteur 0).

Subtilité : la position latérale de l'agent est ANTICIPÉE à l'horizon TTC, pour
distinguer un piéton statique au bord de la voie d'un piéton qui traverse en direction
de la voie.

Sécurité : ce module ATTÉNUE la menace (facteur ≤ 1) ; il ne peut jamais l'amplifier.
Il rétrograde donc le niveau d'un agent hors trajectoire, mais ne fait jamais monter
un niveau — la garantie « pire des métriques » du moteur reste préservée.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .context import Agent

if TYPE_CHECKING:
    from .engine import RiskLevel

DEMI_CORRIDOR_PLEIN_M = 1.5   # menace pleine dans le corridor central
DEMI_CORRIDOR_LARGE_M = 3.5   # ~ 2 voies : au-delà, plus de menace directe


def _cap_a_composantes(cap_deg: float) -> tuple[float, float]:
    """(vitesse longitudinale, vitesse latérale) unitaires, dans le repère ego.

    Convention du projet : cap 0 = même sens que l'ego (avance) ; cap 90 = latéral
    (traverse) ; cap 180 = frontal (face-à-face). Une vitesse latérale positive
    signifie « se rapproche de l'axe de l'ego ».
    """
    r = math.radians(cap_deg)
    # composante longitudinale (peu utilisée ici, mais on l'expose)
    v_long_unit = math.cos(r)
    # composante latérale : « traverse vers l'axe » (sin > 0 sur [0, 180])
    v_lat_unit = -math.sin(r)   # négatif : se rapproche de y = 0 si écart positif
    return v_long_unit, v_lat_unit


def ecart_lateral_projete(agent: Agent, horizon_s: float) -> float:
    """Écart latéral de l'agent à un horizon donné (typiquement le TTC).

    Prend l'écart courant et le fait évoluer selon la composante latérale de la
    vitesse de l'agent, sur `horizon_s` secondes. Convention : un cap dans (0, 180)
    signifie un mouvement transversal ; on suppose que ce mouvement se dirige vers
    l'axe de l'ego (le cas dangereux), c'est-à-dire que |écart| diminue.
    """
    if not math.isfinite(horizon_s) or horizon_s <= 0:
        return agent.ecart_lateral_m
    v_ms = agent.vitesse_kmh / 3.6
    r = math.radians(agent.cap_relatif_deg)
    v_lat = v_ms * abs(math.sin(r))          # amplitude du mouvement latéral
    e0 = agent.ecart_lateral_m
    # On rapproche l'écart de 0 (cas dangereux : l'agent traverse vers l'axe),
    # sans changer de signe (pas de dépassement franc de l'axe dans l'estimation).
    return math.copysign(max(abs(e0) - v_lat * horizon_s, 0.0), e0 if e0 != 0.0 else 1.0)


def facteur_menace(agent: Agent, horizon_s: float,
                   plein: float = DEMI_CORRIDOR_PLEIN_M,
                   large: float = DEMI_CORRIDOR_LARGE_M) -> float:
    """Facteur de menace [0, 1] fondé sur l'écart latéral projeté à l'horizon TTC.

    1 dans le corridor central, décroît linéairement, 0 au-delà de `large`.
    """
    y = abs(ecart_lateral_projete(agent, horizon_s))
    if y <= plein:
        return 1.0
    if y >= large:
        return 0.0
    return (large - y) / (large - plein)


# Palier d'atténuation : au-dessus de ce facteur, aucun changement de niveau
# (on ne rétrograde que si l'agent est clairement hors trajectoire).
def rétrograder(niveau, facteur: float):
    """Rétrograde un niveau selon le facteur de menace (jamais d'amplification).

    facteur ≥ 0.7 : niveau inchangé (agent essentiellement en voie)
    0.4 ≤ facteur < 0.7 : un cran en dessous
    facteur < 0.4 : deux crans en dessous (agent clairement hors trajectoire)
    Le résultat est borné à SAFE.
    """
    from .engine import RiskLevel  # import différé pour éviter le cycle
    if facteur >= 0.7:
        return niveau
    if facteur >= 0.4:
        return RiskLevel(max(int(niveau) - 1, int(RiskLevel.SAFE)))
    return RiskLevel(max(int(niveau) - 2, int(RiskLevel.SAFE)))
