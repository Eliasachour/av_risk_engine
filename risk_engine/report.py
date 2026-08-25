"""
Table des métriques de criticité par agent.

Pour chaque agent d'un ScenarioContext, rassemble les six métriques
(TTC, THW, PET, RSS, CI, DRAC), leur classement individuel, la distance réelle,
le niveau de risque global et la métrique qui le déclenche, puis met le tout en
forme (console ou interface).

Ce module ne dépend ni de CARLA ni de tkinter : purement calculatoire, testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from .context import Agent, ScenarioContext
from .engine import RiskConfig, RiskLevel, assess_agent


@dataclass
class MetriquesAgent:
    """Toutes les métriques + classements pour un agent."""
    agent: Agent
    distance_m: float
    ttc: float          # s (brut)
    ttc_effectif: float # s (brut / marge contextuelle)
    thw: float          # s
    pet: float          # s (croisement ; inf sinon)
    rss_min: float      # m (distance de sécurité RSS)
    ratio_rss: float    # distance réelle / distance RSS
    ci: float           # indice de conflit [0, 1]
    drac: float         # m/s²
    niveau: RiskLevel               # niveau global (pire métrique)
    niveaux: Dict[str, RiskLevel]   # niveau par métrique
    metrique_decisive: str          # métrique(s) imposant le niveau global
    contributions: Dict[str, float] # pertinence x criticité, par métrique
    metrique_impact: str            # métrique de plus forte contribution
    corroboration: int              # nb de métriques concordant au niveau décisif

    @property
    def rss_viole(self) -> bool:
        return self.ratio_rss < 1.0


def metriques_agent(ctx: ScenarioContext, agent: Agent, cfg: RiskConfig) -> MetriquesAgent:
    r = assess_agent(ctx, agent, cfg)
    return MetriquesAgent(
        agent=agent,
        distance_m=agent.distance_m,
        ttc=r.ttc,
        ttc_effectif=r.ttc_effectif,
        thw=r.thw,
        pet=r.pet,
        rss_min=r.rss_min,
        ratio_rss=r.ratio_rss,
        ci=r.ci,
        drac=r.drac,
        niveau=r.level,
        niveaux=r.niveaux,
        metrique_decisive=r.metrique_decisive,
        contributions=r.contributions,
        metrique_impact=r.metrique_impact,
        corroboration=r.corroboration,
    )


def tableau_metriques(
    ctx: ScenarioContext, cfg: Optional[RiskConfig] = None
) -> List[MetriquesAgent]:
    """Calcule les métriques de tous les agents du contexte."""
    cfg = cfg or RiskConfig()
    return [metriques_agent(ctx, a, cfg) for a in ctx.agents]


# ---------- mise en forme texte ----------

_COLS = [
    ("Agent", 10),
    ("dist(m)", 8),
    ("TTC(s)", 8),
    ("THW(s)", 8),
    ("PET(s)", 8),
    ("RSS(m)", 9),
    ("CI", 6),
    ("DRAC", 7),
    ("niveau", 9),
    ("déclencheur", 12),
]


def _fmt(x: float, inf: str = "  inf") -> str:
    if not math.isfinite(x):
        return inf
    return f"{x:.2f}"


def lignes_tableau(table: List[MetriquesAgent]) -> List[List[str]]:
    """Renvoie les lignes (listes de chaînes) prêtes à afficher."""
    lignes = []
    for m in table:
        rss_applique_viole = m.niveaux.get("RSS", RiskLevel.SAFE) >= RiskLevel.DANGER
        rss = f"{m.rss_min:.0f}{'!' if rss_applique_viole else ''}"
        lignes.append([
            m.agent.type_agent.value,
            f"{m.distance_m:.0f}",
            _fmt(m.ttc_effectif),
            _fmt(m.thw),
            _fmt(m.pet),
            rss,
            f"{m.ci:.2f}",
            _fmt(m.drac, inf="   0"),
            str(m.niveau),
            m.metrique_decisive,
        ])
    return lignes


def format_tableau(table: List[MetriquesAgent]) -> str:
    """Table monospace des métriques (pour la console)."""
    if not table:
        return "(aucun agent)"
    entete = " ".join(f"{nom:>{w}}" for nom, w in _COLS)
    sep = "-" * len(entete)
    corps = []
    for ligne in lignes_tableau(table):
        corps.append(" ".join(f"{val:>{w}}" for val, (_, w) in zip(ligne, _COLS)))
    notes = (
        "\nTTC = TTC effectif (brut / marge contextuelle)."
        "\nRSS suivi de '!' = distance réelle < distance de sécurité RSS."
        "\n« déclencheur » = métrique(s) imposant le niveau global."
    )
    return "\n".join([entete, sep, *corps]) + notes


def format_seuils(cfg: Optional[RiskConfig] = None) -> str:
    """Grille des seuils de référence, pour interpréter directement chaque valeur."""
    cfg = cfg or RiskConfig()
    g = lambda x: f"{x:g}"
    L = 12  # largeur de la colonne « métrique »
    lignes = ["Seuils de référence (par métrique : SAFE = valeur sûre) :"]
    for nom, unite, s, w, d in [
        ("TTC", "s", cfg.ttc_safe, cfg.ttc_watch, cfg.ttc_danger),
        ("THW", "s", cfg.thw_safe, cfg.thw_watch, cfg.thw_danger),
        ("PET", "s", cfg.pet_safe, cfg.pet_watch, cfg.pet_danger),
    ]:
        label = f"{nom} ({unite})"
        lignes.append(
            f"  {label:<{L}}SAFE > {g(s):4}| WATCH {g(w)}–{g(s):5}| "
            f"DANGER {g(d)}–{g(w):5}| CRITICAL < {g(d)}"
        )
    lignes.append(f"  {'RSS':<{L}}SAFE : distance ≥ d_rss | sinon violé → {cfg.rss_violation_level.name}")
    for nom, unite, w, d, c in [
        ("CI", "", cfg.ci_watch, cfg.ci_danger, cfg.ci_critical),
        ("DRAC", "m/s²", cfg.drac_watch, cfg.drac_danger, cfg.drac_critical),
    ]:
        label = f"{nom} ({unite})" if unite else nom
        lignes.append(
            f"  {label:<{L}}SAFE < {g(w):4}| WATCH {g(w)}–{g(d):5}| "
            f"DANGER {g(d)}–{g(c):4}| CRITICAL > {g(c)}"
        )
    return "\n".join(lignes)


def format_impact(table: List[MetriquesAgent]) -> str:
    """Résumé de l'impact des métriques par agent (pondération contextuelle)."""
    if not table:
        return ""
    lignes = ["Impact des métriques (pertinence x criticité, décroissant) :"]
    for m in table:
        top = sorted(m.contributions.items(), key=lambda kv: kv[1], reverse=True)
        top = [f"{nom} {val:.2f}" for nom, val in top if val > 0.0][:3]
        classement = " > ".join(top) if top else "—"
        lignes.append(
            f"  {m.agent.type_agent.value:8s} impact={m.metrique_impact:4s} "
            f"corroboration={m.corroboration}  [{classement}]"
        )
    return "\n".join(lignes)
