"""Test de l'optimiseur de seuils : il ne doit JAMAIS introduire de détection
manquée, et ne doit pas dégrader le nombre de fausses alarmes."""
from risk_engine import RiskConfig
from calibration import evaluer, synthese
from optimize import optimiser


def test_optimisation_respecte_la_contrainte_de_securite():
    # L'optimiseur ne doit jamais créer de détection manquée, ni régresser sur
    # les fausses alarmes. Contrainte dure de sécurité.
    base = RiskConfig()
    opt = optimiser(base, passes=3)
    s_base = synthese(evaluer(base))
    s_opt = synthese(evaluer(opt))
    assert s_opt["sous_classements"] == 0
    assert s_opt["surclassements"] <= s_base["surclassements"]
