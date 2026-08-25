"""
Géométrie relative d'un agent — source unique de vérité.

Un `Agent` est décrit par des grandeurs *scalaires* commodes à saisir :
distance, écart latéral, cap relatif. Pour raisonner sur les trajectoires, il
faut les convertir en une pose 2D dans le repère de l'ego. Cette conversion
était jusqu'ici implémentée uniquement dans le simulateur (`sim/kinematic.py`),
ce qui interdisait au moteur de faire de la géométrie 2D : il ne connaissait
que les scalaires.

Ce module extrait cette conversion pour que **le moteur et le simulateur
partagent exactement la même géométrie**. Toute divergence entre les deux
serait un bug silencieux : le simulateur montrerait une trajectoire que le
moteur n'évalue pas.

Convention du repère ego
------------------------
- l'ego est à l'origine, orienté selon ``+x`` ;
- ``+y`` est à sa **droite** ;
- ``cap_relatif_deg`` vaut 0 pour un agent de même sens (suivi), 180 pour un
  face-à-face, 90 pour une traversée ;
- ``ecart_lateral_m`` positif place l'agent à droite. Un agent décalé est
  orienté de sorte que sa composante latérale le **ramène vers l'axe** de
  l'ego : c'est la sémantique « traversée » voulue.
"""
from __future__ import annotations

import math
from typing import Tuple


def pose_agent_relative(
    distance_m: float,
    ecart_lateral_m: float,
    cap_relatif_deg: float,
) -> Tuple[float, float, float]:
    """Convertit (distance, écart latéral, cap) en pose ``(x, y, yaw_deg)``.

    La distance est traitée comme une distance *euclidienne* : un agent à
    \\SI{20}{m} avec \\SI{6}{m} d'écart latéral est donc à
    :math:`x = \\sqrt{20^2 - 6^2} \\approx 19{,}1` m devant, et non 20 m.

    Returns
    -------
    (x, y, yaw_deg)
        Position dans le repère ego et cap absolu dans ce même repère.
    """
    e = ecart_lateral_m
    if e == 0.0:
        return distance_m, 0.0, cap_relatif_deg

    # L'écart latéral ne peut pas excéder la distance euclidienne.
    e = max(-distance_m, min(distance_m, e))
    x = math.sqrt(max(0.0, distance_m ** 2 - e ** 2))
    y = e
    cap = math.radians(cap_relatif_deg)
    # La composante latérale est orientée vers l'axe (y = 0) : si l'agent est à
    # droite (e > 0), il se déplace vers -y ; s'il est à gauche, vers +y.
    yaw = math.degrees(math.atan2(-math.copysign(math.sin(cap), e), math.cos(cap)))
    return x, y, yaw


def vitesse_agent_relative(
    vitesse_ms: float,
    yaw_deg: float,
) -> Tuple[float, float]:
    """Décompose la vitesse d'un agent en ``(vx, vy)`` dans le repère ego."""
    r = math.radians(yaw_deg)
    return vitesse_ms * math.cos(r), vitesse_ms * math.sin(r)
