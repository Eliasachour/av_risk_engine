"""Tests de la grille de seuils : chaque métrique classe selon RiskConfig,
le niveau global est le pire, et la métrique déclencheuse est tracée."""
from risk_engine import (
    Agent,
    RiskConfig,
    RiskLevel,
    ScenarioContext,
    TypeAgent,
    assess_risk,
)
from risk_engine.engine import assess_agent


def _agent_risk(ctx, cfg=None):
    cfg = cfg or RiskConfig()
    return assess_agent(ctx, ctx.agents[0], cfg)


def test_six_metriques_classees():
    ctx = ScenarioContext(
        vitesse_ego_kmh=80,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=30, distance_m=40, cap_relatif_deg=0)],
    )
    ar = _agent_risk(ctx)
    assert set(ar.niveaux) == {"TTC", "THW", "PET", "RSS", "CI", "DRAC"}
    assert ar.level == max(ar.niveaux.values())


def test_niveau_global_est_le_pire():
    ctx = ScenarioContext(
        vitesse_ego_kmh=90,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=0, distance_m=12, cap_relatif_deg=0)],
    )
    ar = _agent_risk(ctx)
    # collision quasi immédiate -> au moins une métrique CRITICAL -> global CRITICAL
    assert ar.level == RiskLevel.CRITICAL
    assert ar.metrique_decisive != "—"


def test_drac_impossible_seuil_fixe_vs_mu():
    # Sur verglas, l'option µ·g doit rendre un DRAC modéré « impossible »
    # là où le seuil fixe 8 m/s² ne le ferait pas.
    from risk_engine.context import EtatRoute

    ctx = ScenarioContext(
        vitesse_ego_kmh=40,
        etat_route=EtatRoute.VERGLAS,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=0, distance_m=30, cap_relatif_deg=0)],
    )
    fixe = assess_agent(ctx, ctx.agents[0], RiskConfig(drac_impossible_via_mu=False))
    via_mu = assess_agent(ctx, ctx.agents[0], RiskConfig(drac_impossible_via_mu=True))
    assert via_mu.niveaux["DRAC"] >= fixe.niveaux["DRAC"]


def test_rss_neutralise_hors_suivi():
    # Conflit de croisement : la borne longitudinale RSS ne doit pas s'appliquer
    ctx = ScenarioContext(
        vitesse_ego_kmh=50,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=30, distance_m=20, cap_relatif_deg=90)],
    )
    ar = _agent_risk(ctx)
    assert ar.niveaux["RSS"] == RiskLevel.SAFE


def test_rss_binaire():
    # En suivi, le RSS est binaire : respecté -> SAFE, violé -> niveau de violation.
    # Distance courte (10 m) face à un véhicule lent : d < d_rss -> violé.
    proche = ScenarioContext(
        vitesse_ego_kmh=90,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=20, distance_m=10, cap_relatif_deg=0)],
    )
    assert _agent_risk(proche).niveaux["RSS"] == RiskConfig().rss_violation_level

    # Grande distance (300 m) : d >= d_rss -> respecté -> SAFE
    loin = ScenarioContext(
        vitesse_ego_kmh=90,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=20, distance_m=300, cap_relatif_deg=0)],
    )
    assert _agent_risk(loin).niveaux["RSS"] == RiskLevel.SAFE


def test_seuils_configurables():
    # En durcissant le seuil TTC, un cas SAFE peut basculer
    ctx = ScenarioContext(
        vitesse_ego_kmh=50,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=20, distance_m=80, cap_relatif_deg=0)],
    )
    doux = assess_agent(ctx, ctx.agents[0], RiskConfig(ttc_safe=4.0))
    dur = assess_agent(ctx, ctx.agents[0], RiskConfig(ttc_safe=20.0))
    assert dur.niveaux["TTC"] >= doux.niveaux["TTC"]
