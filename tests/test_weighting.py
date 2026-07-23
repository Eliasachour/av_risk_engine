"""Tests de la pondération et de la contribution des métriques."""
from risk_engine import Agent, ScenarioContext, TypeAgent, assess_risk
from risk_engine.modifiers import FamilleConflit
from risk_engine import weighting


def test_criticite_bornee_01():
    assert weighting.criticite_haut(10, 4, 1) == 0.0      # très sûr
    assert weighting.criticite_haut(0, 4, 1) == 1.0       # très critique
    assert 0.0 <= weighting.criticite_bas(5, 3, 8) <= 1.0


def test_pet_non_pertinent_en_suivi():
    contribs = weighting.contributions({"PET": 1.0, "TTC": 1.0}, FamilleConflit.SUIVI)
    assert contribs["PET"] == 0.0      # PET neutralisé en suivi
    assert contribs["TTC"] > 0.0


def test_classement_decroissant():
    cl = weighting.classement({"A": 0.2, "B": 0.9, "C": 0.5})
    assert [nom for nom, _ in cl] == ["B", "C", "A"]


def test_impact_et_corroboration_exposes():
    ctx = ScenarioContext(
        vitesse_ego_kmh=50,
        agents=[Agent(TypeAgent.PIETON, vitesse_kmh=5, distance_m=20, cap_relatif_deg=90)],
    )
    d = assess_risk(ctx).details[0]
    assert d.metrique_impact in d.niveaux
    assert d.corroboration >= 0
