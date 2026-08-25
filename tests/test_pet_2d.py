"""Tests du PET géométrique 2D et de l'exclusion du TTC en croisement (D15).

Ces tests verrouillent trois choses :

- la géométrie partagée entre le moteur et le simulateur ;
- le comportement du PET 2D, y compris son horizon de confiance ;
- le fait que l'exclusion du TTC en croisement n'est sûre qu'associée au PET 2D.
"""
import math

import pytest

from risk_engine import (
    Agent,
    RiskConfig,
    RiskLevel,
    ScenarioContext,
    TypeAgent,
    assess_risk,
    metrics,
)
from risk_engine.geometry import pose_agent_relative, vitesse_agent_relative


# ---------------------------------------------------------------------------
# Géométrie partagée
# ---------------------------------------------------------------------------


def test_pose_sans_ecart_lateral():
    x, y, yaw = pose_agent_relative(40.0, 0.0, 90.0)
    assert x == 40.0 and y == 0.0 and yaw == 90.0


def test_pose_avec_ecart_lateral_conserve_la_distance():
    """La distance saisie est euclidienne : x = sqrt(d^2 - e^2)."""
    d, e = 20.0, 6.0
    x, y, _ = pose_agent_relative(d, e, 90.0)
    assert y == pytest.approx(e)
    assert math.hypot(x, y) == pytest.approx(d)


def test_pose_agent_a_droite_traverse_vers_la_gauche():
    """Un agent décalé à droite doit se déplacer VERS l'axe de l'ego."""
    _, y, yaw = pose_agent_relative(20.0, +6.0, 90.0)
    _, vy = vitesse_agent_relative(1.4, yaw)
    assert y > 0 and vy < 0, "l'agent à droite doit avoir une vitesse vers -y"


def test_pose_agent_a_gauche_traverse_vers_la_droite():
    _, y, yaw = pose_agent_relative(20.0, -6.0, 90.0)
    _, vy = vitesse_agent_relative(1.4, yaw)
    assert y < 0 and vy > 0, "l'agent à gauche doit avoir une vitesse vers +y"


# ---------------------------------------------------------------------------
# PET 2D
# ---------------------------------------------------------------------------


def test_pet_2d_infini_en_conflit_longitudinal():
    """Suivi et face-à-face relèvent du TTC, pas du PET : trajectoire parallèle."""
    assert not math.isfinite(metrics.pet_2d(22.0, 16.0, 40.0, 0.0, 0.0))
    assert not math.isfinite(metrics.pet_2d(22.0, 16.0, 60.0, 180.0, 0.0))


def test_pet_2d_infini_si_ego_arrete():
    assert not math.isfinite(metrics.pet_2d(0.0, 1.4, 20.0, 90.0, 5.0))


def test_pet_2d_nul_si_trajectoires_se_recoupent():
    """Piéton déjà dans le couloir, ego qui arrive : les créneaux se recouvrent."""
    pet = metrics.pet_2d(13.9, 1.4, 8.0, 90.0, 0.0)
    assert pet == 0.0


def test_pet_2d_mesure_une_coincidence_pas_une_proximite():
    """Le PET n'est PAS monotone en écart latéral — et c'est correct.

    Contre-intuitif mais physiquement juste : le PET mesure la coïncidence
    temporelle entre deux passages, pas une distance. Pour un ego à 50 km/h et
    un piéton à 30 m qui traverse à 5 km/h, on mesure :

    ==========  ========
    écart       PET
    ==========  ========
    12 m        5,22 s
     8 m        2,26 s
     4 m        0,00 s   <- coïncidence : ils y sont ensemble
     1 m        0,07 s   <- le piéton vient de dégager
    ==========  ========

    Le minimum est à un écart INTERMÉDIAIRE. À 1 m, le piéton a presque fini de
    traverser quand l'ego arrive ; à 12 m, il n'a pas encore commencé. C'est le
    sens même du Post-Encroachment Time, et c'est ce que l'ancien PET
    « snapshot » (distance / v_ego) était incapable d'exprimer.
    """
    def _pet(e):
        return metrics.pet_2d(13.9, 1.4, 30.0, 90.0, e, horizon_s=20.0)

    loin, moyen, coincidence = _pet(12.0), _pet(8.0), _pet(4.0)

    # Un agent encore loin de la voie laisse une marge confortable.
    assert loin > moyen > coincidence
    # La coïncidence est bien détectée comme trajectoire de collision.
    assert coincidence == 0.0
    # Et le minimum n'est pas à l'écart le plus faible : non-monotonie assumée.
    assert _pet(1.0) > coincidence


def test_pet_2d_horizon_de_confiance():
    """Un conflit prévu au-delà de l'horizon n'est pas évalué.

    Prédire qu'un piéton entrera dans la voie dans six secondes suppose qu'il
    marchera à vitesse constante pendant six secondes — hypothèse intenable.
    Le moteur préfère ne rien affirmer plutôt que d'affirmer faux.
    """
    # Piéton loin sur le côté : le conflit se noue tard.
    tard = metrics.pet_2d(13.9, 1.4, 80.0, 90.0, 10.0, horizon_s=4.0)
    assert not math.isfinite(tard)
    # Le même conflit est bien évalué si on relâche l'horizon.
    relache = metrics.pet_2d(13.9, 1.4, 80.0, 90.0, 10.0, horizon_s=20.0)
    assert math.isfinite(relache)


# ---------------------------------------------------------------------------
# Intégration moteur : les deux changements ne valent qu'ensemble
# ---------------------------------------------------------------------------


def _compteurs(cfg):
    """Renvoie (exactitude, manquées, fausses) sur le jeu de référence."""
    from calibration import REFERENCES

    rang = {"SAFE": 0, "WATCH": 1, "DANGER": 2, "CRITICAL": 3}
    exact = manquees = fausses = 0
    for ref in REFERENCES:
        predit = assess_risk(ref.ctx, cfg).level.name
        attendu = ref.niveau_attendu.name
        if predit == attendu:
            exact += 1
        elif rang[predit] < rang[attendu]:
            manquees += 1
        else:
            fausses += 1
    return exact, manquees, fausses


def test_exclure_le_ttc_seul_casse_la_securite():
    """Neutraliser le TTC en croisement SANS PET 2D produit des manquées.

    Résultat mesuré qui justifie D15 : les deux changements sont indissociables.
    On ne peut retirer le TTC d'un régime que si une autre métrique valide y
    prend le relais.
    """
    _, manquees, _ = _compteurs(
        RiskConfig(pet_2d=False, ttc_hors_croisement=True)
    )
    assert manquees > 0, (
        "ce test documente une régression attendue : s'il passe à 0 manquée, "
        "c'est que le moteur a changé et que D15 doit être réexaminé"
    )


def test_configuration_par_defaut_sure_et_meilleure():
    """La configuration par défaut : 0 manquée, et meilleure que sans D15."""
    exact_d15, manq_d15, faux_d15 = _compteurs(RiskConfig())
    exact_av, manq_av, faux_av = _compteurs(
        RiskConfig(pet_2d=False, ttc_hors_croisement=False)
    )

    assert manq_d15 == 0, "la contrainte de sécurité reste absolue"
    assert exact_d15 >= exact_av, "D15 ne doit pas dégrader l'exactitude"
    assert faux_d15 <= faux_av, "D15 ne doit pas ajouter de fausse alarme"


def test_pieton_lointain_lateral_reste_safe():
    """SC-12 : piéton qui commence à traverser à 10 m de la voie, ego à 80 m.

    Avant D15, le TTC (invalide en croisement) classait ce cas en WATCH. Le
    conflit se noue à plus de 6 s : hors horizon de confiance, donc non évalué.
    """
    ctx = ScenarioContext(
        vitesse_ego_kmh=50,
        agents=[Agent(TypeAgent.PIETON, vitesse_kmh=5, distance_m=80,
                      cap_relatif_deg=90, ecart_lateral_m=10)],
    )
    assert assess_risk(ctx).level == RiskLevel.SAFE
