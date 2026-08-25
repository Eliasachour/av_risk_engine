"""Tests du harnais de calibration sur les scénarios de référence."""
from risk_engine import RiskLevel
from calibration import evaluer, matrice_confusion, synthese


def test_jeu_de_reference_fourni():
    from calibration.scenarios_ref import REFERENCES
    res = evaluer()
    assert len(res) == len(REFERENCES) >= 20   # jeu élargi (>= 20 scénarios)


def test_matrice_somme_totale():
    res = evaluer()
    M = matrice_confusion(res)
    total = sum(M[a][p] for a in M for p in M[a])
    assert total == len(res)


def test_synthese_coherente():
    res = evaluer()
    s = synthese(res)
    assert s["corrects"] + s["surclassements"] + s["sous_classements"] == s["n"]


def test_ancres_non_ambigues():
    # Scénarios dont le verdict ne doit pas bouger : repères de non-régression
    par_id = {r.cas.id: r.predit for r in evaluer()}
    assert par_id["SC-01"] == RiskLevel.SAFE       # véhicule frontal lointain
    assert par_id["SC-06"] == RiskLevel.CRITICAL   # cycliste traversant à 25 m


def test_aucune_detection_manquee():
    # Contrainte de sécurité invariante : zéro détection manquée sur les scénarios
    # de référence. Le raffinement de la méthode d'étiquetage (durcissement contextuel
    # conditionné à TTC < 2 s, voir ETIQUETAGE.md) rétablit cet invariant.
    assert synthese(evaluer())["sous_classements"] == 0
