import math

from risk_engine import (
    Agent,
    ScenarioContext,
    TypeAgent,
    format_tableau,
    tableau_metriques,
)
from risk_engine.report import lignes_tableau


def _ctx():
    return ScenarioContext(
        vitesse_ego_kmh=80,
        agents=[
            Agent(TypeAgent.VOITURE, vitesse_kmh=30, distance_m=40, cap_relatif_deg=0),
            Agent(TypeAgent.PIETON, vitesse_kmh=5, distance_m=30, cap_relatif_deg=90),
        ],
    )


def test_tableau_un_par_agent():
    t = tableau_metriques(_ctx())
    assert len(t) == 2


def test_metriques_completes():
    m = tableau_metriques(_ctx())[0]
    # toutes les métriques demandées sont présentes
    for champ in ("ttc", "thw", "pet", "rss_min", "ci", "drac"):
        assert hasattr(m, champ)
    assert 0.0 <= m.ci <= 1.0


def test_pet_present_pour_croisement():
    # le second agent est un croisement (cap 90) -> PET fini
    m = tableau_metriques(_ctx())[1]
    assert math.isfinite(m.pet)


def test_lignes_et_format():
    t = tableau_metriques(_ctx())
    lignes = lignes_tableau(t)
    assert len(lignes) == 2
    assert all(len(l) == 10 for l in lignes)  # 10 colonnes
    txt = format_tableau(t)
    assert "TTC(s)" in txt and "CI" in txt and "PET(s)" in txt


def test_format_sans_agent():
    ctx = ScenarioContext(vitesse_ego_kmh=50, agents=[])
    assert format_tableau(tableau_metriques(ctx)) == "(aucun agent)"
