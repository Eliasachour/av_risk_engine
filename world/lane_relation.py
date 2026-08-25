"""
Relation de voie — qui roule où, et est-ce que nos trajectoires se croisent.

Pourquoi ce module existe
-------------------------
Jusqu'ici, la perception ne transmettait au moteur qu'un **écart latéral
euclidien** : la distance perpendiculaire à l'axe *instantané* de l'ego. Sur
ligne droite, c'est juste. En virage, c'est faux — et dangereusement faux.

Mesure faite sur le projet : un véhicule **arrêté dans la voie de l'ego, à
40 m**, sur un virage de rayon 200 m, présente un écart latéral euclidien de
4 m. Le filtrage latéral le rétrograde alors en SAFE. À 80 m de rayon, l'écart
monte à 9,8 m. C'est une **détection manquée**, précisément ce que le moteur
s'interdit.

La cause est géométrique : l'écart euclidien mesure l'éloignement d'une
*droite*, alors que la route est une *courbe*. Il faut donc raisonner en
coordonnées de voie — ce que CARLA expose via ses waypoints.

Ce que fournit ce module
------------------------
- ``RelationVoie`` : la nature du rapport entre deux véhicules (même voie,
  adjacente, opposée, route différente, convergente).
- ``analyser`` : calcule cette relation à partir des waypoints CARLA
  (``road_id``, ``lane_id``, ``section_id``, orientation), et surtout un
  **écart latéral curviligne** qui reste juste en virage.

Le module vit dans ``world/`` et non dans ``risk_engine/`` : le moteur reste
ignorant de CARLA (D9). Il ne reçoit qu'un écart latéral — simplement, un
écart désormais mesuré le long de la route plutôt qu'à vol d'oiseau.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RelationVoie(Enum):
    """Rapport géométrique entre la voie de l'ego et celle d'un autre véhicule."""

    MEME_VOIE = "meme_voie"
    """Même route, même voie, même sens. Conflit longitudinal direct."""

    VOIE_ADJACENTE = "voie_adjacente"
    """Même route, même sens, voie voisine. Pas de conflit sauf déboîtement."""

    VOIE_OPPOSEE = "voie_opposee"
    """Même route, sens inverse. Pas de conflit tant que chacun tient sa voie."""

    ROUTE_DIFFERENTE = "route_differente"
    """Routes distinctes qui ne se rejoignent pas à l'horizon considéré."""

    CONVERGENTE = "convergente"
    """Routes distinctes, mais qui se rejoignent devant — typiquement une
    intersection ou une bretelle d'insertion. C'est le cas où un véhicule
    éloigné et hors de ma voie peut malgré tout devenir un conflit."""

    INDETERMINEE = "indeterminee"
    """Position non projetable sur le réseau (hors route, données manquantes).
    Traité de façon conservatrice : on ne rétrograde pas."""


#: Relations pour lesquelles un conflit longitudinal est possible.
RELATIONS_CONFLICTUELLES = frozenset({
    RelationVoie.MEME_VOIE,
    RelationVoie.CONVERGENTE,
    RelationVoie.INDETERMINEE,
})


@dataclass(frozen=True)
class AnalyseVoie:
    """Résultat de l'analyse pour un véhicule donné.

    Attributs
    ---------
    relation : RelationVoie
    ecart_lateral_m : float
        Écart latéral **curviligne**, signé (positif à droite de l'ego). C'est
        cette valeur qui est transmise au moteur, à la place de l'écart
        euclidien. En virage, elle reste proche de zéro pour un véhicule de la
        même voie — ce que l'euclidien ne sait pas faire.
    distance_curviligne_m : float | None
        Distance mesurée le long de la route, quand les deux véhicules sont sur
        la même route. ``None`` sinon.
    devant : bool
        Vrai si l'autre véhicule est devant l'ego dans son sens de marche.
    ecart_voies : int
        Nombre de voies séparant les deux véhicules (0 = même voie).
    meme_sens : bool
    """
    relation: RelationVoie
    ecart_lateral_m: float
    distance_curviligne_m: Optional[float] = None
    devant: bool = True
    ecart_voies: int = 0
    meme_sens: bool = True
    cap_relatif_deg: float = 0.0
    """Cap relatif mesuré **par rapport aux directions de voie**, et non en
    absolu. Sur une route courbe, deux véhicules qui suivent chacun leur voie
    présentent un écart de cap absolu non nul — purement dû à la courbure.
    Extrapolé en ligne droite, cet écart fait croire à une convergence : c'est
    ainsi qu'un véhicule de la voie adjacente, roulant parallèlement, était
    classé CRITICAL. En retranchant l'orientation de la voie sous chaque
    véhicule, un déplacement parfaitement parallèle redonne bien 0°."""

    @property
    def conflit_possible(self) -> bool:
        """Un conflit longitudinal est-il envisageable dans cette relation ?"""
        return self.relation in RELATIONS_CONFLICTUELLES


# ---------------------------------------------------------------------------
# Helpers géométriques
# ---------------------------------------------------------------------------


def _ecart_signe(ego_tf, point) -> float:
    """Écart latéral signé d'un point par rapport à l'axe de l'ego (m)."""
    dx = point.x - ego_tf.location.x
    dy = point.y - ego_tf.location.y
    yaw = math.radians(ego_tf.rotation.yaw)
    return -dx * math.sin(yaw) + dy * math.cos(yaw)


def _devant(ego_tf, point) -> bool:
    """Le point est-il devant l'ego, dans son sens de marche ?"""
    dx = point.x - ego_tf.location.x
    dy = point.y - ego_tf.location.y
    yaw = math.radians(ego_tf.rotation.yaw)
    return (dx * math.cos(yaw) + dy * math.sin(yaw)) > 0.0


def _ecart_angulaire(yaw_a_deg: float, yaw_b_deg: float) -> float:
    """Écart signé entre deux caps, ramené dans [-180, 180]."""
    return (yaw_a_deg - yaw_b_deg + 180.0) % 360.0 - 180.0


def _meme_sens(yaw_a_deg: float, yaw_b_deg: float, tolerance_deg: float = 90.0) -> bool:
    """Deux caps pointent-ils globalement dans le même sens ?"""
    ecart = abs((yaw_a_deg - yaw_b_deg + 180.0) % 360.0 - 180.0)
    return ecart < tolerance_deg


# ---------------------------------------------------------------------------
# Analyse principale
# ---------------------------------------------------------------------------


def analyser(
    carte,
    ego_tf,
    autre_tf,
    horizon_convergence_m: float = 60.0,
) -> AnalyseVoie:
    """Détermine la relation de voie entre l'ego et un autre véhicule.

    Parameters
    ----------
    carte : carla.Map
    ego_tf, autre_tf : carla.Transform
    horizon_convergence_m : float
        Distance sur laquelle on cherche si deux routes distinctes se
        rejoignent. Au-delà, on considère qu'elles ne se croisent pas dans un
        futur pertinent.

    Notes
    -----
    Si la projection sur le réseau échoue (véhicule hors route, carte
    indisponible), on renvoie ``INDETERMINEE`` avec l'écart euclidien. C'est le
    comportement conservateur : le moteur continuera d'évaluer normalement
    plutôt que de rétrograder un agent qu'on ne sait pas situer.
    """
    ecart_euclidien = _ecart_signe(ego_tf, autre_tf.location)
    devant = _devant(ego_tf, autre_tf.location)

    try:
        import carla
        wp_ego = carte.get_waypoint(ego_tf.location, project_to_road=True,
                                    lane_type=carla.LaneType.Driving)
        wp_autre = carte.get_waypoint(autre_tf.location, project_to_road=True,
                                      lane_type=carla.LaneType.Driving)
    except (ImportError, RuntimeError, AttributeError):
        wp_ego = wp_autre = None

    if wp_ego is None or wp_autre is None:
        return AnalyseVoie(RelationVoie.INDETERMINEE, ecart_euclidien,
                           devant=devant)

    meme_route = (getattr(wp_ego, "road_id", None) == getattr(wp_autre, "road_id", None))
    lane_ego = getattr(wp_ego, "lane_id", 0)
    lane_autre = getattr(wp_autre, "lane_id", 0)
    largeur = getattr(wp_ego, "lane_width", 3.5) or 3.5

    # --- Cas 1 : routes différentes ---------------------------------------
    if not meme_route:
        relation = _relation_hors_route(wp_ego, wp_autre, horizon_convergence_m)
        return AnalyseVoie(
            relation, ecart_euclidien, devant=devant,
            meme_sens=_meme_sens(ego_tf.rotation.yaw, autre_tf.rotation.yaw),
            cap_relatif_deg=_ecart_angulaire(autre_tf.rotation.yaw,
                                             ego_tf.rotation.yaw),
        )

    # --- Cas 2 : même route -----------------------------------------------
    # Le signe de `lane_id` code le sens de parcours par rapport à l'axe de
    # référence de la route : deux signes opposés = sens de circulation opposés.
    meme_sens = (lane_ego * lane_autre) > 0
    ecart_voies = abs(lane_ego - lane_autre)

    # Écart latéral CURVILIGNE : combien de voies nous séparent, plus le
    # décalage de l'autre véhicule par rapport à l'axe de SA voie. Le résultat
    # ne dépend plus de la courbure de la route.
    decalage_dans_sa_voie = _ecart_signe(wp_autre.transform, autre_tf.location)
    if lane_ego == lane_autre:
        ecart_curviligne = decalage_dans_sa_voie
    else:
        # Signe : la voie est-elle à droite ou à gauche de l'ego ? On s'appuie
        # sur l'écart euclidien, fiable pour le SIGNE même s'il l'est mal pour
        # l'amplitude en virage.
        signe = 1.0 if ecart_euclidien >= 0 else -1.0
        ecart_curviligne = signe * (ecart_voies * largeur) + decalage_dans_sa_voie

    if not meme_sens:
        relation = RelationVoie.VOIE_OPPOSEE
    elif lane_ego == lane_autre:
        relation = RelationVoie.MEME_VOIE
    else:
        relation = RelationVoie.VOIE_ADJACENTE

    # Cap relatif corrigé : écart de chacun par rapport à SA voie, plus 180°
    # si les voies sont de sens opposés.
    devi_ego = _ecart_angulaire(ego_tf.rotation.yaw, wp_ego.transform.rotation.yaw)
    devi_autre = _ecart_angulaire(autre_tf.rotation.yaw, wp_autre.transform.rotation.yaw)
    cap_rel = devi_autre - devi_ego + (0.0 if meme_sens else 180.0)
    cap_rel = (cap_rel + 180.0) % 360.0 - 180.0

    # Distance le long de la route, quand les abscisses curvilignes existent.
    s_ego = getattr(wp_ego, "s", None)
    s_autre = getattr(wp_autre, "s", None)
    d_curv = abs(s_autre - s_ego) if (s_ego is not None and s_autre is not None) else None

    return AnalyseVoie(
        relation=relation,
        ecart_lateral_m=ecart_curviligne,
        distance_curviligne_m=d_curv,
        devant=devant,
        ecart_voies=ecart_voies,
        meme_sens=meme_sens,
        cap_relatif_deg=cap_rel,
    )


def _relation_hors_route(wp_ego, wp_autre, horizon_m: float) -> RelationVoie:
    """Deux routes distinctes se rejoignent-elles devant l'ego ?

    On avance le long de la voie de l'ego et on regarde si l'on atteint la
    route de l'autre véhicule, ou une intersection. C'est le cas typique du
    croisement : le véhicule n'est pas dans ma voie, mais nos trajectoires se
    rencontrent.
    """
    route_cible = getattr(wp_autre, "road_id", None)
    wp = wp_ego
    parcouru = 0.0
    pas = 5.0
    while parcouru < horizon_m:
        suivants = wp.next(pas)
        if not suivants:
            break
        wp = suivants[0]
        parcouru += pas
        if getattr(wp, "road_id", None) == route_cible:
            return RelationVoie.CONVERGENTE
        if getattr(wp, "is_junction", False):
            # Une intersection devant : les trajectoires peuvent se croiser.
            return RelationVoie.CONVERGENTE
    return RelationVoie.ROUTE_DIFFERENTE
