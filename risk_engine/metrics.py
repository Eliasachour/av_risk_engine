"""
Métriques de criticité (fonctions pures).

Correspondance avec le tableau de l'état de l'art (§4) :
    - TTC   : métrique temporelle
    - THW   : métrique temporelle (temps inter-véhiculaire)
    - PET   : métrique temporelle (croisement) — estimation instantanée
    - DRAC  : métrique fondée sur la décélération
    - RSS   : modèle de sécurité formel (Shalev-Shwartz et al., 2017)
    - CI    : indice de conflit composite (imminence × sévérité), normalisé [0, 1]

Modèle de rapprochement : la vitesse de fermeture est la projection de la
vitesse relative sur la ligne ego->agent, paramétrée par le cap relatif.
    cap   0° (même sens)   -> closing = v_ego - v_agent
    cap 180° (face-à-face) -> closing = v_ego + v_agent
    cap  90° (croisement)  -> closing = v_ego
C'est une approximation 1D ; les conflits purement latéraux gagneraient à être
traités par le PET (nécessite des données temporelles, hors périmètre frame-à-frame).
"""
from __future__ import annotations

import math

KMH_TO_MS = 1.0 / 3.6
G = 9.81  # m/s²


def to_ms(kmh: float) -> float:
    """Convertit une vitesse de km/h en m/s."""
    return kmh * KMH_TO_MS


def closing_speed(v_ego_ms: float, v_agent_ms: float, cap_deg: float) -> float:
    """Vitesse de rapprochement (m/s), projetée sur la ligne ego->agent."""
    return v_ego_ms - v_agent_ms * math.cos(math.radians(cap_deg))


def ttc(v_ego_ms: float, v_agent_ms: float, distance_m: float, cap_deg: float) -> float:
    """Time-To-Collision (s) à VITESSE constante. Renvoie +inf si pas d'approche."""
    c = closing_speed(v_ego_ms, v_agent_ms, cap_deg)
    if c <= 0.0:
        return math.inf
    return distance_m / c


def ttc_accel(
    v_ego_ms: float,
    v_agent_ms: float,
    distance_m: float,
    cap_deg: float,
    a_agent_ms2: float,
) -> float:
    """Time-To-Collision (s) à ACCÉLÉRATION constante.

    L'agent accélère ou freine (a_agent_ms2) ; l'ego est supposé à vitesse
    constante. On résout la fermeture du gap g(t) = d − v_c·t − ½·a_c·t² = 0,
    où v_c est la vitesse de fermeture et a_c = −a_agent·cos(cap) son accélération.

    Garde physique : un agent qui freine s'ARRÊTE (sa vitesse ne devient pas
    négative) au lieu de repartir en arrière — au-delà de l'arrêt, le gap n'est
    plus fermé que par l'ego. Se réduit exactement au TTC à vitesse constante
    quand a_agent = 0. Renvoie +inf si la collision n'a pas lieu.
    """
    cos = math.cos(math.radians(cap_deg))
    v_c = v_ego_ms - v_agent_ms * cos      # vitesse de fermeture initiale
    a_c = -a_agent_ms2 * cos               # accélération de fermeture (ego constant)

    # instant où l'agent s'arrête (vitesse nulle), s'il freine
    if a_agent_ms2 < 0 and v_agent_ms > 0:
        t_stop = -v_agent_ms / a_agent_ms2
    elif a_agent_ms2 < 0 and v_agent_ms == 0:
        t_stop = 0.0
    else:
        t_stop = math.inf

    # Phase 1 (0 <= t <= t_stop) : ½·a_c·t² + v_c·t − d = 0
    if abs(a_c) < 1e-9:
        t1 = distance_m / v_c if v_c > 1e-9 else math.inf
    else:
        disc = v_c * v_c + 2.0 * a_c * distance_m
        if disc < 0:
            t1 = math.inf
        else:
            sq = math.sqrt(disc)
            cands = [t for t in ((-v_c + sq) / a_c, (-v_c - sq) / a_c) if t > 1e-9]
            t1 = min(cands) if cands else math.inf

    if t1 <= t_stop:
        return t1

    # Phase 2 : agent arrêté à t_stop, gap restant fermé par l'ego seul
    if not math.isfinite(t_stop):
        return math.inf
    g_stop = distance_m - v_c * t_stop - 0.5 * a_c * t_stop * t_stop
    if g_stop <= 0:
        return t_stop
    if v_ego_ms > 1e-9:
        return t_stop + g_stop / v_ego_ms
    return math.inf


def thw(v_ego_ms: float, distance_m: float) -> float:
    """Time Headway (s) : temps pour atteindre la position actuelle de l'agent."""
    if v_ego_ms <= 0.0:
        return math.inf
    return distance_m / v_ego_ms


def drac(v_ego_ms: float, v_agent_ms: float, distance_m: float, cap_deg: float) -> float:
    """Deceleration Rate to Avoid Crash (m/s²) : décélération requise pour éviter la collision."""
    c = closing_speed(v_ego_ms, v_agent_ms, cap_deg)
    if c <= 0.0 or distance_m <= 0.0:
        return 0.0
    return c * c / (2.0 * distance_m)


def braking_distance(v_ms: float, mu: float, g: float = G) -> float:
    """Distance de freinage (m) : d = v² / (2·µ·g)."""
    return v_ms * v_ms / (2.0 * mu * g)


def _est_croisement(cap_deg: float) -> bool:
    """Vrai si le cap correspond à un conflit de croisement (≈ 45°–135°)."""
    c = abs(cap_deg) % 360.0
    return 45.0 <= c <= 135.0 or 225.0 <= c <= 315.0


def pet(v_ego_ms: float, v_agent_ms: float, distance_m: float, cap_deg: float) -> float:
    """Post-Encroachment Time (s) — estimation instantanée à vitesse constante.

    Le PET mesure l'écart temporel entre l'instant où un usager quitte la zone
    de conflit et celui où l'autre y arrive. Il n'a de sens que pour les conflits
    de CROISEMENT (le suivi et le face-à-face relèvent du TTC).

    Modèle « snapshot » : on prend la position courante de l'agent comme point de
    conflit. L'agent est en train de le quitter (t ≈ 0) ; l'ego l'atteint en
    distance / v_ego. D'où PET ≈ distance / v_ego pour un croisement.
    Renvoie +inf hors croisement ou si l'ego est à l'arrêt.

    La valeur EXACTE (avant/après réel) est fournie par la simulation, qui suit
    les positions au cours du temps ; cette fonction n'en donne qu'une estimation.
    """
    if not _est_croisement(cap_deg):
        return math.inf
    if v_ego_ms <= 0.0:
        return math.inf
    return distance_m / v_ego_ms


def conflict_index(
    v_ego_ms: float,
    v_agent_ms: float,
    distance_m: float,
    cap_deg: float,
    a_max: float = 0.9 * G,
    t_ref: float = 4.0,
    a_agent_ms2: float = 0.0,
) -> float:
    """Conflict Index (indice de conflit) — composite normalisé dans [0, 1].

    Produit de deux facteurs complémentaires (cf. familles de Westhofen et al.) :
      - imminence (temporelle) : c_imm = max(0, 1 - TTC / t_ref)
      - sévérité  (freinage)   : c_sev = min(1, DRAC / a_max)
    CI = c_imm · c_sev. Élevé SEULEMENT si le conflit est à la fois imminent ET
    coûteux à éviter ; 0 sinon (pas d'approche, TTC >= t_ref, ou DRAC <= 0).
    La forme multiplicative encode une conjonction (« et »), ce qui distingue le
    CI des métriques prises isolément.

    a_max : décélération disponible (m/s²), typiquement µ·g (dépend de la route).
    t_ref : horizon temporel de référence (s), p. ex. le seuil TTC « sûr ».

    NB : indice de synthèse explicite et ajustable ; il n'existe pas de définition
    canonique du « CI » dans la littérature.
    """
    if closing_speed(v_ego_ms, v_agent_ms, cap_deg) <= 0.0:
        return 0.0
    t = ttc_accel(v_ego_ms, v_agent_ms, distance_m, cap_deg, a_agent_ms2)
    if not math.isfinite(t):
        return 0.0
    c_imm = max(0.0, 1.0 - t / t_ref)
    c_sev = min(1.0, drac(v_ego_ms, v_agent_ms, distance_m, cap_deg) / a_max) if a_max > 0 else 1.0
    return c_imm * c_sev


def rss_min_distance(
    v_rear_ms: float,
    v_front_ms: float,
    rho: float = 0.5,
    a_accel: float = 2.0,
    b_min: float = 4.0,
    b_max: float = 8.0,
) -> float:
    """Distance longitudinale minimale de sécurité au sens RSS (m).

    rho     : temps de réponse de l'ego (s)
    a_accel : accélération max de l'ego pendant rho (m/s²)
    b_min   : décélération minimale garantie de l'ego (m/s²)
    b_max   : décélération maximale supposée du véhicule de tête (m/s²)
    """
    d = (
        v_rear_ms * rho
        + 0.5 * a_accel * rho * rho
        + (v_rear_ms + rho * a_accel) ** 2 / (2.0 * b_min)
        - v_front_ms ** 2 / (2.0 * b_max)
    )
    return max(0.0, d)
