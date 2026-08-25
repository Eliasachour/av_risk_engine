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


# --- Dimensions de la zone de conflit (m) ------------------------------------
#: Demi-largeur du couloir de l'ego (véhicule ~1,8 m de large).
DEMI_LARGEUR_EGO = 0.9
#: Demi-longueur de l'ego (véhicule ~4,7 m de long).
DEMI_LONGUEUR_EGO = 2.35
#: Rayon d'encombrement d'un agent, ajouté aux deux dimensions.
RAYON_AGENT = 0.5
#: Horizon de confiance du PET géométrique (s). Au-delà, l'hypothèse de vitesse
#: constante n'est plus tenable : un piéton qui commencerait à traverser dans
#: six secondes peut tout aussi bien s'arrêter, regarder, ou changer d'allure.
#: Prédire un conflit à cet horizon relève de l'intention, pas de la cinématique.
#: Valeur alignée sur T_ref de l'indice de criticité (4 s).
HORIZON_PET_S = 4.0


def pet_2d(
    v_ego_ms: float,
    v_agent_ms: float,
    distance_m: float,
    cap_deg: float,
    ecart_lateral_m: float = 0.0,
    demi_largeur: float = DEMI_LARGEUR_EGO,
    demi_longueur: float = DEMI_LONGUEUR_EGO,
    rayon_agent: float = RAYON_AGENT,
    horizon_s: float = HORIZON_PET_S,
) -> float:
    """Post-Encroachment Time **géométrique** (s), calculé en 2D.

    Contrairement à :func:`pet`, qui assimilait le point de conflit à la
    position courante de l'agent (et renvoyait donc ``distance / v_ego``
    indépendamment de l'écart latéral), cette version construit réellement la
    zone de conflit et compare les créneaux d'occupation des deux usagers.

    Méthode
    -------
    1. L'ego occupe un **couloir** ``|y| <= demi_largeur + rayon_agent``.
    2. On calcule l'intervalle ``[t_in, t_out]`` pendant lequel l'agent est
       dans ce couloir (résolution de ``y_a + v_y t = ±w``).
    3. Pendant cet intervalle, l'agent balaie une plage longitudinale ; c'est
       la **zone de conflit** en ``x``, élargie de l'encombrement des corps.
    4. On calcule l'intervalle pendant lequel l'ego occupe cette même plage.
    5. Le PET est l'écart entre les deux créneaux. S'ils se **recouvrent**, les
       deux usagers sont dans la zone au même moment : PET = 0 (trajectoires
       de collision).

    Retourne ``+inf`` quand le PET n'est pas défini : agent parallèle au
    couloir (le conflit est alors longitudinal et relève du TTC), ego à
    l'arrêt, ou agent qui ne croisera jamais le couloir.

    Notes
    -----
    Le signe est perdu volontairement : on renvoie une marge temporelle
    positive, comme les autres métriques temporelles du moteur. Savoir *qui*
    passe en premier n'entre pas dans la décision de risque.
    """
    if v_ego_ms <= 0.0:
        return math.inf

    from .geometry import pose_agent_relative, vitesse_agent_relative

    x_a, y_a, yaw_a = pose_agent_relative(distance_m, ecart_lateral_m, cap_deg)
    v_x, v_y = vitesse_agent_relative(v_agent_ms, yaw_a)

    w = demi_largeur + rayon_agent
    long_totale = demi_longueur + rayon_agent

    # --- 1. Créneau d'occupation du couloir par l'agent ---------------------
    if abs(v_y) < 1e-6:
        # Trajectoire parallèle au couloir : jamais de franchissement. Le
        # conflit est longitudinal, c'est au TTC de le traiter.
        return math.inf

    t_bord_1 = (-w - y_a) / v_y
    t_bord_2 = (w - y_a) / v_y
    ta_in, ta_out = min(t_bord_1, t_bord_2), max(t_bord_1, t_bord_2)

    if ta_out <= 0.0 and ta_in <= 0.0:
        # L'agent a déjà traversé le couloir (ou s'en éloigne définitivement).
        # Il n'y a plus de conflit à venir de son fait.
        return math.inf

    # --- 2. Zone de conflit en x, balayée par l'agent pendant son passage ---
    x_debut = x_a + v_x * max(ta_in, 0.0)
    x_fin = x_a + v_x * ta_out
    x_min = min(x_debut, x_fin) - long_totale
    x_max = max(x_debut, x_fin) + long_totale

    if x_max < 0.0:
        # La zone de conflit est entièrement derrière l'ego : il l'a dépassée.
        return math.inf

    # --- 3. Créneau d'occupation de cette zone par l'ego -------------------
    te_in = (x_min - demi_longueur) / v_ego_ms
    te_out = (x_max + demi_longueur) / v_ego_ms

    # --- 4. Horizon de confiance -------------------------------------------
    # Si le conflit se noue au-delà de l'horizon, la prédiction à vitesse
    # constante n'est pas fiable : on ne renvoie pas de PET plutôt que d'en
    # renvoyer un faux. Les autres métriques (TTC, THW, RSS, DRAC) continuent
    # d'évaluer la situation ; elles ne dépendent pas, elles, d'une projection
    # comportementale à plusieurs secondes.
    debut_conflit = min(max(ta_in, 0.0), max(te_in, 0.0))
    if debut_conflit > horizon_s:
        return math.inf

    # --- 5. Écart entre les deux créneaux ---------------------------------
    if ta_in <= te_out and te_in <= ta_out:
        return 0.0                      # recouvrement : trajectoires de collision
    if ta_out < te_in:
        return te_in - ta_out           # l'agent passe d'abord
    return ta_in - te_out               # l'ego passe d'abord
