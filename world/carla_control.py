"""
Helpers de contrôle CARLA — pilotage latéral, reprise ACC.

Version stabilisée avec Gain Scheduling pour éliminer les zigzags
à basse vitesse et lors des phases de freinage/reprise ACC.
"""
from __future__ import annotations

import math


def pilotage_lateral(pont, ego_tf, v_ego_ms: float, gain: float = 0.6) -> float:
    """Contrôle latéral lissé : suivi de voie via waypoint CARLA avec Gain Scheduling.

    Parameters
    ----------
    pont : CarlaBridge
        Pont CARLA fournissant l'accès au monde et à la carte.
    ego_tf : carla.Transform
        Transform courant de l'ego (position + orientation).
    v_ego_ms : float
        Vitesse de l'ego en m/s.
    gain : float
        Gain proportionnel nominal (réglé par défaut à 0.6 pour la stabilité).

    Returns
    -------
    float
        Angle de braquage adouci dans [-0.75, 0.75].
    """
    import carla

    world_map = pont.world.get_map()
    
    # 1. Lookahead adaptatif et lissé :
    # En augmentant la distance plancher à 7m, on évite de réagir aux micro-variations
    d_look = max(7.0, min(18.0, 5.0 + v_ego_ms * 0.8))
    
    wp_ego = world_map.get_waypoint(
        ego_tf.location, project_to_road=True, lane_type=carla.LaneType.Driving,
    )
    if wp_ego is None:
        return 0.0
        
    wps_next = wp_ego.next(d_look)
    if not wps_next:
        return 0.0
    wp = wps_next[0]

    # Vecteur ego → waypoint (plan XY)
    dx = wp.transform.location.x - ego_tf.location.x
    dy = wp.transform.location.y - ego_tf.location.y

    # Écart de cap signé dans [-π, π]
    cap_cible = math.atan2(dy, dx)
    cap_ego = math.radians(ego_tf.rotation.yaw)
    err = math.atan2(math.sin(cap_cible - cap_ego), math.cos(cap_cible - cap_ego))

    # 2. Gain Scheduling :
    # Réduit la sensibilité du volant à basse vitesse (< 15 km/h)
    facteur_vitesse = min(1.0, max(0.35, v_ego_ms / 4.0))
    gain_effectif = gain * facteur_vitesse

    # 3. Angle borné pour éviter les embardées
    steer = err * gain_effectif
    return max(-0.75, min(0.75, steer))


def reprise_acc(cmd_mode: str, v_ego_ms: float, v_cible_ms: float,
                gain: float = 0.8, throttle_max: float = 0.5) -> float:
    """Reprise ACC progressive : réaccélération fluide vers la vitesse cible.

    Parameters
    ----------
    cmd_mode : str
        Mode courant de la commande recommandée ("nominal", "proportionnel", "physique").
    v_ego_ms : float
        Vitesse courante de l'ego en m/s.
    v_cible_ms : float
        Vitesse cible en m/s.
    gain : float
        Gain proportionnel (lissé à 0.8 pour éviter les départs brusques).
    throttle_max : float
        Plafond de l'accélérateur (limité à 0.5 pour une conduite réaliste).
    """
    if cmd_mode != "nominal":
        return 0.0
    if v_ego_ms >= v_cible_ms - 0.3:
        return 0.0
    
    # Montée en vitesse progressive
    delta_v = v_cible_ms - v_ego_ms
    consigne = gain * (delta_v / max(v_cible_ms, 2.0))
    return min(consigne, throttle_max)