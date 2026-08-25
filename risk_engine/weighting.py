from __future__ import annotations

from typing import Dict, List, Tuple

from .modifiers import FamilleConflit

# Pertinence de chaque métrique selon la famille de conflit (0 = non pertinente).
# Fondé sur l'analyse de pertinence de Westhofen et al. : le TTC convient au suivi,
# le PET au croisement, la borne RSS au seul suivi longitudinal, etc.
POIDS: Dict[FamilleConflit, Dict[str, float]] = {
    FamilleConflit.SUIVI:       {"TTC": 1.0, "THW": 1.0, "PET": 0.0, "RSS": 1.0, "CI": 1.0, "DRAC": 1.0},
    FamilleConflit.CROISEMENT:  {"TTC": 0.7, "THW": 0.0, "PET": 1.0, "RSS": 0.0, "CI": 0.8, "DRAC": 0.6},
    FamilleConflit.FACE_A_FACE: {"TTC": 1.0, "THW": 0.3, "PET": 0.0, "RSS": 0.0, "CI": 1.0, "DRAC": 1.0},
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def criticite_haut(v: float, safe: float, danger: float) -> float:
    """Criticité normalisée [0,1] pour une métrique où plus haut = plus sûr."""
    if not (safe > danger) or v != v:        # bornes invalides ou NaN
        return 0.0
    return _clamp01((safe - v) / (safe - danger))


def criticite_bas(v: float, debut: float, critique: float) -> float:
    """Criticité normalisée [0,1] pour une métrique où plus haut = plus dangereux."""
    if not (critique > debut) or v != v:
        return 0.0
    return _clamp01((v - debut) / (critique - debut))


def contributions(criticites: Dict[str, float], famille: FamilleConflit) -> Dict[str, float]:
    """Contribution = pertinence contextuelle x criticité normalisée, par métrique."""
    poids = POIDS.get(famille, {})
    return {m: poids.get(m, 1.0) * s for m, s in criticites.items()}


def classement(contribs: Dict[str, float]) -> List[Tuple[str, float]]:
    """Métriques triées par contribution décroissante (la 1re a le plus d'impact)."""
    return sorted(contribs.items(), key=lambda kv: kv[1], reverse=True)
