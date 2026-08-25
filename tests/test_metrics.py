import math

from risk_engine import metrics


def test_ttc_suivi():
    # ego 20 m/s, agent 10 m/s même sens, 50 m -> closing 10 -> TTC 5 s
    assert math.isclose(metrics.ttc(20, 10, 50, 0), 5.0, rel_tol=1e-6)


def test_ttc_face_a_face():
    # cap 180 -> closing = v_ego + v_agent = 30 -> 50/30
    assert math.isclose(metrics.ttc(20, 10, 50, 180), 50 / 30, rel_tol=1e-6)


def test_ttc_croisement():
    # cap 90 -> closing = v_ego (composante agent nulle) -> 50/20
    assert math.isclose(metrics.ttc(20, 10, 50, 90), 2.5, rel_tol=1e-6)


def test_ttc_non_approche():
    # ego plus lent que l'agent devant -> pas de rapprochement -> +inf
    assert metrics.ttc(10, 20, 50, 0) == math.inf


def test_thw():
    assert math.isclose(metrics.thw(20, 50), 2.5, rel_tol=1e-6)


def test_drac():
    # closing 10, distance 50 -> 100 / 100 = 1.0 m/s²
    assert math.isclose(metrics.drac(20, 10, 50, 0), 1.0, rel_tol=1e-6)


def test_braking_distance():
    # v=20 m/s, mu=0.9 -> 400 / (2*0.9*9.81)
    assert math.isclose(metrics.braking_distance(20, 0.9), 400 / (2 * 0.9 * 9.81), rel_tol=1e-6)


def test_rss_min_distance():
    d = metrics.rss_min_distance(25.0, 8.333, rho=0.5, a_accel=2.0, b_min=4.0, b_max=8.0)
    assert math.isclose(d, 92.9, abs_tol=0.5)


def test_ttc_accel_reduit_au_constant():
    # a_agent = 0 -> identique au TTC à vitesse constante
    assert math.isclose(metrics.ttc_accel(25, 10, 60, 0, 0.0),
                        metrics.ttc(25, 10, 60, 0), rel_tol=1e-6)


def test_ttc_accel_freinage_lead_plus_court():
    # véhicule de tête (20 m/s) qui freine fort (-8) : TTC bien plus court
    cv = metrics.ttc(25, 20, 40, 0)            # = 40/5 = 8 s
    ca = metrics.ttc_accel(25, 20, 40, 0, -8.0)
    assert ca < cv
    assert math.isclose(ca, 2.6, abs_tol=0.1)


def test_ttc_accel_lead_accelere_pas_de_collision():
    # véhicule de tête qui accélère : il s'échappe -> pas de collision
    assert metrics.ttc_accel(25, 20, 40, 0, 2.0) == math.inf


def test_ttc_accel_garde_arret():
    # agent déjà à l'arrêt avec a négatif : il ne « recule » pas
    # -> obstacle statique, TTC = d / v_ego = 40/25 = 1.6 s
    assert math.isclose(metrics.ttc_accel(25, 0, 40, 0, -8.0), 1.6, abs_tol=1e-6)


def test_pet_croisement():
    # cap 90 (croisement), ego 20 m/s, 50 m -> PET ≈ 50/20 = 2.5 s
    assert math.isclose(metrics.pet(20, 10, 50, 90), 2.5, rel_tol=1e-6)


def test_pet_suivi_indefini():
    # cap 0 (suivi) -> PET non défini -> +inf
    assert metrics.pet(20, 10, 50, 0) == math.inf


def test_pet_face_a_face_indefini():
    # cap 180 (face-à-face) -> hors croisement -> +inf
    assert metrics.pet(20, 10, 50, 180) == math.inf


def test_conflict_index_borne():
    ci = metrics.conflict_index(20, 10, 50, 0)
    assert 0.0 <= ci <= 1.0


def test_conflict_index_non_approche_nul():
    # ego plus lent que l'agent devant -> pas de conflit -> CI = 0
    assert metrics.conflict_index(10, 20, 50, 0) == 0.0


def test_conflict_index_croit_quand_distance_diminue():
    # plus l'agent est proche, plus le CI est élevé (TTC plus court)
    loin = metrics.conflict_index(20, 0, 100, 0)
    pres = metrics.conflict_index(20, 0, 10, 0)
    assert pres > loin
