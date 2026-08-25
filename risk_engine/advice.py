"""
Recommandations d'action — que faire pour revenir en zone sûre.

Le moteur dit *où en est* la situation ; ce module dit *quoi faire*. Il produit
des consignes **chiffrées et vérifiables** — « ralentir de 18 km/h » plutôt que
« ralentir » — à destination d'un conducteur, notamment en apprentissage.

Principe de calcul : **inverser le moteur, pas le réimplémenter.**
Plutôt que de recoder l'inverse analytique de chacune des six métriques (six
formules à maintenir, six occasions de diverger du moteur), on cherche par
dichotomie la vitesse la plus élevée qui ramène le verdict au niveau visé. Le
moteur reste l'unique source de vérité : toute évolution de ses seuils se
répercute automatiquement sur les recommandations.

Cette inversion n'est licite que parce que le niveau de risque est **monotone
croissant** en vitesse de l'ego — propriété vérifiée par
``tests/test_invariants.py::test_monotonie_vitesse_ego``.

Limites assumées
----------------
- Aucune recommandation latérale (changer de voie, se déporter) : le moteur ne
  modélise pas la trajectoire latérale (D11).
- Aucune connaissance du code de la route : la consigne peut suggérer une
  vitesse inférieure à ce qu'autoriserait la situation réglementaire.
- La recommandation décrit l'instant présent. Elle ne planifie pas.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional

from .context import ScenarioContext
from .engine import RiskAssessment, RiskConfig, RiskLevel, assess_risk


class TypeAction(str, Enum):
    """Nature de l'action recommandée."""
    AUCUNE = "aucune"
    MAINTENIR = "maintenir"
    RALENTIR = "ralentir"
    FREINER_FORT = "freiner_fort"
    ARRET_IMPOSSIBLE = "arret_impossible"


@dataclass(frozen=True)
class Recommandation:
    """Consigne d'action, chiffrée quand c'est possible.

    Attributs
    ---------
    action : TypeAction
        Nature de l'action.
    delta_vitesse_kmh : float | None
        De combien réduire la vitesse. ``None`` si non applicable.
    vitesse_cible_kmh : float | None
        Vitesse à atteindre.
    distance_sure_m : float | None
        Distance à laquelle le conflit courant redeviendrait sûr, à vitesse
        inchangée. Informatif : on ne « crée » pas de la distance, on l'obtient
        en ralentissant ou en attendant.
    message : str
        Consigne courte, à afficher.
    justification : str
        Pourquoi — la métrique en cause et sa valeur.
    urgence : int
        0 = aucune, 1 = anticiper, 2 = agir, 3 = agir immédiatement.
    """
    action: TypeAction
    message: str
    justification: str
    urgence: int
    delta_vitesse_kmh: Optional[float] = None
    vitesse_cible_kmh: Optional[float] = None
    distance_sure_m: Optional[float] = None


# ---------------------------------------------------------------------------
# Inversion du moteur
# ---------------------------------------------------------------------------


def vitesse_max_pour_niveau(
    ctx: ScenarioContext,
    niveau_cible: RiskLevel = RiskLevel.SAFE,
    cfg: Optional[RiskConfig] = None,
    tolerance_kmh: float = 0.5,
) -> Optional[float]:
    """Vitesse la plus élevée qui maintient le verdict à ``niveau_cible`` ou mieux.

    Recherche par dichotomie sur ``ctx.vitesse_ego_kmh``. Renvoie ``None`` si
    même l'arrêt complet ne suffit pas — cas d'un agent qui fonce sur un ego
    immobile, où ralentir ne résout rien.
    """
    cfg = cfg or RiskConfig()
    rang_cible = int(niveau_cible)

    def niveau(v: float) -> int:
        return int(assess_risk(replace(ctx, vitesse_ego_kmh=v), cfg).level)

    v_haut = ctx.vitesse_ego_kmh
    if niveau(v_haut) <= rang_cible:
        return v_haut                      # déjà conforme
    if niveau(0.0) > rang_cible:
        return None                        # même à l'arrêt, insuffisant

    v_bas = 0.0
    while v_haut - v_bas > tolerance_kmh:
        milieu = (v_bas + v_haut) / 2.0
        if niveau(milieu) <= rang_cible:
            v_bas = milieu
        else:
            v_haut = milieu
    return v_bas


def distance_sure_pour_niveau(
    ctx: ScenarioContext,
    indice_agent: int = 0,
    niveau_cible: RiskLevel = RiskLevel.SAFE,
    cfg: Optional[RiskConfig] = None,
    distance_max_m: float = 300.0,
    tolerance_m: float = 0.5,
) -> Optional[float]:
    """Distance à laquelle le conflit redeviendrait sûr, vitesse inchangée.

    Utile pédagogiquement : « à cette vitesse, il vous faudrait 62 m ». On ne
    recommande pas d'« augmenter la distance » comme une action immédiate —
    c'est une conséquence du ralentissement, pas une commande.
    """
    cfg = cfg or RiskConfig()
    if not ctx.agents or indice_agent >= len(ctx.agents):
        return None
    rang_cible = int(niveau_cible)

    def niveau(d: float) -> int:
        agents = list(ctx.agents)
        agents[indice_agent] = replace(agents[indice_agent], distance_m=d)
        return int(assess_risk(replace(ctx, agents=agents), cfg).level)

    if niveau(distance_max_m) > rang_cible:
        return None                        # même très loin, ça ne suffit pas

    d_bas = ctx.agents[indice_agent].distance_m
    d_haut = distance_max_m
    while d_haut - d_bas > tolerance_m:
        milieu = (d_bas + d_haut) / 2.0
        if niveau(milieu) <= rang_cible:
            d_haut = milieu
        else:
            d_bas = milieu
    return d_haut


# ---------------------------------------------------------------------------
# Recommandation
# ---------------------------------------------------------------------------

#: Libellés lisibles des métriques, pour la justification.
_LIBELLES = {
    "TTC": "temps avant collision",
    "THW": "temps inter-véhiculaire",
    "PET": "marge de croisement",
    "RSS": "distance de sécurité",
    "CI": "indice de criticité",
    "DRAC": "freinage requis",
}


def recommander(
    ctx: ScenarioContext,
    evaluation: Optional[RiskAssessment] = None,
    cfg: Optional[RiskConfig] = None,
    niveau_cible: RiskLevel = RiskLevel.SAFE,
) -> Recommandation:
    """Produit la consigne d'action correspondant à la situation courante."""
    cfg = cfg or RiskConfig()
    evaluation = evaluation or assess_risk(ctx, cfg)

    # --- Situation déjà sûre ------------------------------------------------
    if int(evaluation.level) <= int(niveau_cible):
        if not ctx.agents:
            return Recommandation(
                action=TypeAction.AUCUNE,
                message="Voie libre",
                justification="Aucun usager détecté dans le champ de perception.",
                urgence=0,
            )
        return Recommandation(
            action=TypeAction.MAINTENIR,
            message="Situation maîtrisée",
            justification=f"{len(ctx.agents)} usager(s) suivi(s), tous à distance sûre.",
            urgence=0,
        )

    # --- Agent le plus critique et métrique en cause ------------------------
    pire = max(evaluation.details, key=lambda d: int(d.level))
    indice = evaluation.details.index(pire)
    metrique = pire.metrique_decisive or "?"
    libelle = _LIBELLES.get(metrique, metrique)
    type_agent = pire.agent.type_agent.value

    # --- Combien ralentir ? -------------------------------------------------
    v_cible = vitesse_max_pour_niveau(ctx, niveau_cible, cfg)
    d_sure = distance_sure_pour_niveau(ctx, indice, niveau_cible, cfg)

    if v_cible is None:
        # Ralentir ne suffit pas : le conflit persiste même à l'arrêt.
        return Recommandation(
            action=TypeAction.ARRET_IMPOSSIBLE,
            message="FREINEZ — conflit non évitable par la seule vitesse",
            justification=(
                f"{libelle} critique face à {type_agent} ; "
                "réduire la vitesse ne suffit pas à revenir en zone sûre."
            ),
            urgence=3,
            distance_sure_m=d_sure,
        )

    delta = ctx.vitesse_ego_kmh - v_cible
    if delta < 1.0:
        # Marginal : la situation est à la frontière.
        return Recommandation(
            action=TypeAction.MAINTENIR,
            message="Vigilance — situation à la limite",
            justification=f"{libelle} proche du seuil face à {type_agent}.",
            urgence=1,
            vitesse_cible_kmh=v_cible,
            distance_sure_m=d_sure,
        )

    # --- Consigne chiffrée --------------------------------------------------
    urgence = {RiskLevel.WATCH: 1, RiskLevel.DANGER: 2,
               RiskLevel.CRITICAL: 3}.get(evaluation.level, 2)
    action = TypeAction.FREINER_FORT if urgence == 3 else TypeAction.RALENTIR
    verbe = "FREINEZ" if urgence == 3 else "Ralentissez"

    message = f"{verbe} de {delta:.0f} km/h  ({ctx.vitesse_ego_kmh:.0f} -> {v_cible:.0f} km/h)"

    # La métrique décisive peut en concaténer plusieurs (« TTC+RSS+DRAC ») :
    # on détaille la première reconnue, les autres sont mentionnées.
    codes = [c for c in metrique.replace("+", " ").split() if c in _LIBELLES]
    principal = codes[0] if codes else metrique

    detail = {
        "THW": f"temps inter-véhiculaire de {pire.thw:.1f} s (usage : 2 s)",
        "TTC": f"{pire.ttc:.1f} s avant collision au rythme actuel",
        "RSS": f"distance de sécurité de {pire.rss_min:.0f} m non tenue",
        "DRAC": f"freinage requis de {pire.drac:.1f} m/s²",
        "PET": f"marge de croisement de {pire.pet:.1f} s",
        "CI": f"indice de criticité à {pire.ci:.2f}",
    }.get(principal, _LIBELLES.get(principal, principal))

    justif = f"{type_agent.capitalize()} : {detail}"
    if len(codes) > 1:
        autres = ", ".join(codes[1:])
        justif += f" — également signalé par {autres}"

    return Recommandation(
        action=action,
        message=message,
        justification=justif,
        urgence=urgence,
        delta_vitesse_kmh=delta,
        vitesse_cible_kmh=v_cible,
        distance_sure_m=d_sure,
    )
