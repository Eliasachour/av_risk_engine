"""
Modificateurs contextuels.

Ils traduisent l'idée centrale du moteur : un même TTC brut n'a pas la même
gravité selon le contexte. Chaque modificateur renvoie un facteur >= 1 ;
leur produit forme la « marge » par laquelle on divise le TTC brut pour obtenir
un TTC effectif (plus le contexte est défavorable, plus le TTC effectif chute).

Sources :
    - multiplicateurs de friction : légende du tableau de scénarios (Wong, 2008)
    - seuils de visibilité : Bijelic et al. 2018, Kutila et al. 2018 + AASHTO
    - distinction profondeur mesurée/inférée : pénalité d'incertitude
"""
from __future__ import annotations

from enum import Enum

from .context import EtatRoute, TypeAgent

MU_SEC = 0.9  # coefficient d'adhérence de référence (chaussée sèche)

# Multiplicateur sur la distance de freinage (légende du tableau, ABS supposé actif)
FRICTION_MULTIPLIER = {
    EtatRoute.SEC: 1.0,
    EtatRoute.MOUILLE: 1.4,
    EtatRoute.NEIGEUX: 1.8,
    EtatRoute.VERGLAS: 3.0,
}


def friction_multiplier(etat: EtatRoute) -> float:
    return FRICTION_MULTIPLIER[etat]


def mu(etat: EtatRoute) -> float:
    """Coefficient d'adhérence, cohérent avec le multiplicateur (µ = µ_sec / multiplicateur)."""
    return MU_SEC / FRICTION_MULTIPLIER[etat]


# Les usagers vulnérables (VRU) imposent une marge plus prudente.
AGENT_FACTOR = {
    TypeAgent.VOITURE: 1.0,
    TypeAgent.CAMION: 1.0,
    TypeAgent.CYCLISTE: 1.3,
    TypeAgent.PIETON: 1.5,
    TypeAgent.OUVRIER: 1.5,
}


def agent_factor(t: TypeAgent) -> float:
    return AGENT_FACTOR[t]


class ClasseVisibilite(Enum):
    NOMINALE = "nominale"
    REDUITE = "reduite"
    DEGRADEE = "degradee"
    CRITIQUE = "critique"


def classe_visibilite(vis_m: float) -> ClasseVisibilite:
    """Seuils : >300 nominale, 100-300 réduite, 40-100 dégradée, <40 critique."""
    if vis_m > 300.0:
        return ClasseVisibilite.NOMINALE
    if vis_m >= 100.0:
        return ClasseVisibilite.REDUITE
    if vis_m >= 40.0:
        return ClasseVisibilite.DEGRADEE
    return ClasseVisibilite.CRITIQUE


VISIBILITY_FACTOR = {
    ClasseVisibilite.NOMINALE: 1.0,
    ClasseVisibilite.REDUITE: 1.2,
    ClasseVisibilite.DEGRADEE: 1.6,
    ClasseVisibilite.CRITIQUE: 2.5,
}


def visibility_factor(vis_m: float) -> float:
    return VISIBILITY_FACTOR[classe_visibilite(vis_m)]


UNCERTAINTY_FACTOR_INFERRED = 1.3


def uncertainty_factor(profondeur_mesuree: bool) -> float:
    """Pénalité d'incertitude : profondeur inférée (caméra) -> marge accrue."""
    return 1.0 if profondeur_mesuree else UNCERTAINTY_FACTOR_INFERRED


class FamilleConflit(Enum):
    SUIVI = "suivi"
    CROISEMENT = "croisement"
    FACE_A_FACE = "face_a_face"
    AUTRE = "autre"


def famille_conflit(cap_deg: float) -> FamilleConflit:
    """Classe le conflit selon le cap (légende : 0° suivi, 45-90° croisement, 160-180° face-à-face)."""
    c = abs(cap_deg) % 360.0
    if c <= 20.0 or c >= 340.0:
        return FamilleConflit.SUIVI
    if 45.0 <= c <= 135.0:
        return FamilleConflit.CROISEMENT
    if 160.0 <= c <= 200.0:
        return FamilleConflit.FACE_A_FACE
    return FamilleConflit.AUTRE
