"""
Moteur de risque : classe chaque métrique selon une grille de seuils (RiskConfig),
retient le pire niveau par agent puis par scénario, et calcule la contribution de
chaque métrique. Voir README.md pour les choix de conception (TTC effectif, RSS
binaire en suivi). Le module ne dépend ni de CARLA ni de tkinter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional

from . import metrics, modifiers, weighting, lateral
from .context import Agent, ScenarioContext
from .sanitize import sanitize_context


class RiskLevel(IntEnum):
    SAFE = 0
    WATCH = 1
    DANGER = 2
    CRITICAL = 3

    def __str__(self) -> str:
        return self.name


@dataclass
class RiskConfig:
    # --- TTC (s), appliqués au TTC EFFECTIF (brut / marge) ; plus haut = plus sûr
    ttc_safe: float = 4.0       # >= safe        -> SAFE
    ttc_watch: float = 2.0      # [watch, safe)  -> WATCH
    ttc_danger: float = 1.0     # [danger, watch)-> DANGER ; < danger -> CRITICAL
    # --- THW (s) ; plus haut = plus sûr
    thw_safe: float = 2.0
    thw_watch: float = 1.0
    thw_danger: float = 0.5
    # --- PET (s), conflits de croisement ; plus haut = plus sûr
    pet_safe: float = 3.0
    pet_watch: float = 1.5
    pet_danger: float = 0.5
    # --- RSS : modèle binaire fidèle à Shalev-Shwartz et al. — la distance de
    # sécurité d_rss est une frontière PROUVÉE (respectée / violée), pas une
    # échelle graduée. Si la distance réelle passe sous d_rss, le RSS est violé
    # et reçoit un niveau d'alerte unique ; la gradation fine est laissée aux
    # métriques cinématiques (TTC, DRAC...).
    rss_violation_level: RiskLevel = RiskLevel.DANGER  # niveau si d_réel < d_rss
    # --- CI (indice de conflit, [0,1]) ; plus bas = plus sûr
    ci_watch: float = 0.3       # < 0.3          -> SAFE
    ci_danger: float = 0.6      # [0.3, 0.6)     -> WATCH
    ci_critical: float = 0.85   # [0.6, 0.85)    -> DANGER ; >= 0.85 -> CRITICAL
    # --- DRAC (m/s²) ; plus bas = plus sûr
    drac_watch: float = 3.0     # < 3            -> SAFE
    drac_danger: float = 6.0    # [3, 6)         -> WATCH
    drac_critical: float = 8.0  # [6, 8)         -> DANGER ; >= 8 -> CRITICAL
    # Si True, le seuil « impossible » du DRAC devient l'adhérence réelle µ·g
    # (plus juste sur chaussée dégradée : ~2.9 m/s² sur verglas) au lieu du 8 fixe.
    drac_impossible_via_mu: bool = False
    # Si True (défaut), le TTC est calculé à accélération constante (utilise
    # l'accélération de l'agent) ; sinon à vitesse constante.
    ttc_constant_accel: bool = True
    # --- Paramètres du calcul de la distance de sécurité RSS
    rho: float = 0.5
    a_accel: float = 2.0
    b_min: float = 4.0
    b_max: float = 8.0


@dataclass
class AgentRisk:
    agent: Agent
    level: RiskLevel
    ttc: float
    ttc_effectif: float
    thw: float
    pet: float
    drac: float
    rss_min: float
    ratio_rss: float
    ci: float
    marge: float
    niveaux: Dict[str, RiskLevel]      # niveau par métrique
    metrique_decisive: str             # métrique(s) imposant le niveau global
    raison: str
    contributions: Dict[str, float] = field(default_factory=dict)  # pertinence x criticité
    metrique_impact: str = "—"         # métrique de plus forte contribution
    corroboration: int = 0             # nb de métriques concordant au niveau décisif


@dataclass
class RiskAssessment:
    level: RiskLevel
    agent_critique: Optional[Agent]
    details: List[AgentRisk] = field(default_factory=list)
    avertissements: List[str] = field(default_factory=list)  # corrections d'assainissement

    def __str__(self) -> str:
        if self.agent_critique is None:
            return f"[{self.level}] aucun agent"
        return (
            f"[{self.level}] agent critique = {self.agent_critique.type_agent.value} "
            f"à {self.agent_critique.distance_m:.0f} m"
        )


# ---------- classement d'une métrique ----------

def _band_haut(v: float, safe: float, watch: float, danger: float) -> RiskLevel:
    """Plus la valeur est haute, plus c'est sûr (TTC, THW, PET, ratio RSS)."""
    if v >= safe:
        return RiskLevel.SAFE
    if v >= watch:
        return RiskLevel.WATCH
    if v >= danger:
        return RiskLevel.DANGER
    return RiskLevel.CRITICAL


def _band_bas(v: float, watch: float, danger: float, critical: float) -> RiskLevel:
    """Plus la valeur est basse, plus c'est sûr (CI, DRAC)."""
    if v < watch:
        return RiskLevel.SAFE
    if v < danger:
        return RiskLevel.WATCH
    if v < critical:
        return RiskLevel.DANGER
    return RiskLevel.CRITICAL


def assess_agent(ctx: ScenarioContext, agent: Agent, cfg: RiskConfig) -> AgentRisk:
    v_ego = metrics.to_ms(ctx.vitesse_ego_kmh)
    v_ag = metrics.to_ms(agent.vitesse_kmh)
    cap = agent.cap_relatif_deg
    d = agent.distance_m

    # --- métriques brutes
    a_ag = agent.acceleration_ms2
    if cfg.ttc_constant_accel:
        raw_ttc = metrics.ttc_accel(v_ego, v_ag, d, cap, a_ag)
    else:
        raw_ttc = metrics.ttc(v_ego, v_ag, d, cap)
    _thw = metrics.thw(v_ego, d)
    _pet = metrics.pet(v_ego, v_ag, d, cap)
    _drac = metrics.drac(v_ego, v_ag, d, cap)
    rss = metrics.rss_min_distance(v_ego, v_ag, cfg.rho, cfg.a_accel, cfg.b_min, cfg.b_max)
    a_max = modifiers.mu(ctx.etat_route) * metrics.G  # décélération disponible (µ·g)
    _ci = metrics.conflict_index(v_ego, v_ag, d, cap, a_max=a_max, t_ref=cfg.ttc_safe, a_agent_ms2=a_ag)
    ratio_rss = d / rss if rss > 0 else math.inf

    # --- marge contextuelle (appliquée au TTC seulement)
    marge = (
        modifiers.friction_multiplier(ctx.etat_route)
        * modifiers.agent_factor(agent.type_agent)
        * modifiers.visibility_factor(ctx.visibilite_m)
        * modifiers.uncertainty_factor(agent.profondeur_mesuree)
    )
    ttc_eff = raw_ttc / marge if math.isfinite(raw_ttc) else math.inf

    # --- classement métrique par métrique
    approche = metrics.closing_speed(v_ego, v_ag, cap) > 0.0
    suivi = modifiers.famille_conflit(cap) is modifiers.FamilleConflit.SUIVI

    n_ttc = _band_haut(ttc_eff, cfg.ttc_safe, cfg.ttc_watch, cfg.ttc_danger)
    n_thw = _band_haut(_thw, cfg.thw_safe, cfg.thw_watch, cfg.thw_danger)
    n_pet = _band_haut(_pet, cfg.pet_safe, cfg.pet_watch, cfg.pet_danger)
    # RSS : binaire, valable seulement en conflit longitudinal (suivi) et si l'ego
    # approche. Respecté (d >= d_rss) -> SAFE ; violé (d < d_rss) -> niveau unique.
    if suivi and approche and d < rss:
        n_rss = cfg.rss_violation_level
    else:
        n_rss = RiskLevel.SAFE
    n_ci = _band_bas(_ci, cfg.ci_watch, cfg.ci_danger, cfg.ci_critical)
    drac_crit = a_max if cfg.drac_impossible_via_mu else cfg.drac_critical
    n_drac = _band_bas(_drac, cfg.drac_watch, cfg.drac_danger, drac_crit)

    niveaux: Dict[str, RiskLevel] = {
        "TTC": n_ttc, "THW": n_thw, "PET": n_pet,
        "RSS": n_rss, "CI": n_ci, "DRAC": n_drac,
    }

    level = max(niveaux.values())

    # --- filtrage latéral 2D : atténuation d'un agent hors trajectoire.
    # Fonde le facteur de menace sur l'écart latéral projeté à l'horizon TTC.
    # Contrainte de sécurité : on NE rétrograde JAMAIS un usager vulnérable (VRU)
    # qui traverse — la garantie de zéro détection manquée l'exige. On ne
    # rétrograde que les agents motorisés clairement hors trajectoire.
    horizon = ttc_eff if math.isfinite(ttc_eff) else cfg.ttc_safe
    facteur = lateral.facteur_menace(agent, horizon)
    est_vru = agent.type_agent in (modifiers.TypeAgent.PIETON,
                                    modifiers.TypeAgent.CYCLISTE,
                                    modifiers.TypeAgent.OUVRIER)
    if est_vru:
        # VRU : jamais rétrograder. Cohérent avec la méthode d'étiquetage qui
        # confirme le durcissement dès que TTC < 2 s OU trajectoire projetée < 2 m.
        # La prudence maximale sur l'usager vulnérable prime sur la réduction des
        # fausses alarmes — on préserve ainsi la contrainte de zéro détection manquée.
        level_ajuste = level
    else:
        level_ajuste = lateral.rétrograder(level, facteur)
    if level_ajuste < level:
        level = level_ajuste
        decisives = []
    else:
        decisives = [m for m, lv in niveaux.items() if lv == level and lv > RiskLevel.SAFE]
    metrique_decisive = "+".join(decisives) if decisives else "—"
    raison = "; ".join(f"{m}={lv}" for m, lv in niveaux.items())

    # --- pondération : criticité normalisée x pertinence contextuelle
    famille = modifiers.famille_conflit(cap)
    criticites = {
        "TTC": weighting.criticite_haut(ttc_eff, cfg.ttc_safe, cfg.ttc_danger),
        "THW": weighting.criticite_haut(_thw, cfg.thw_safe, cfg.thw_danger),
        "PET": weighting.criticite_haut(_pet, cfg.pet_safe, cfg.pet_danger),
        "RSS": 1.0 if n_rss > RiskLevel.SAFE else 0.0,
        "CI": weighting.criticite_bas(_ci, cfg.ci_watch, cfg.ci_critical),
        "DRAC": weighting.criticite_bas(_drac, cfg.drac_watch, drac_crit),
    }
    contribs = weighting.contributions(criticites, famille)
    classt = weighting.classement(contribs)
    metrique_impact = classt[0][0] if classt and classt[0][1] > 0.0 else "—"

    return AgentRisk(
        agent=agent, level=level,
        ttc=raw_ttc, ttc_effectif=ttc_eff, thw=_thw, pet=_pet,
        drac=_drac, rss_min=rss, ratio_rss=ratio_rss, ci=_ci, marge=marge,
        niveaux=niveaux, metrique_decisive=metrique_decisive, raison=raison,
        contributions=contribs, metrique_impact=metrique_impact,
        corroboration=len(decisives),
    )


def assess_risk(ctx: ScenarioContext, cfg: Optional[RiskConfig] = None) -> RiskAssessment:
    """Évalue le risque du contexte : pire niveau parmi tous les agents."""
    cfg = cfg or RiskConfig()
    ctx, avertissements = sanitize_context(ctx)
    if not ctx.agents:
        return RiskAssessment(RiskLevel.SAFE, None, [], avertissements)
    details = [assess_agent(ctx, a, cfg) for a in ctx.agents]
    pire = max(details, key=lambda d: d.level)
    return RiskAssessment(pire.level, pire.agent, details, avertissements)
