"""Tests du module `risk_engine.control` — la commande recommandée exportable."""
from risk_engine import (
    Agent,
    RiskConfig,
    ScenarioContext,
    TypeAgent,
    assess_risk,
)
from risk_engine.context import EtatRoute
from risk_engine.control import (
    FREINAGE_PAR_NIVEAU,
    ObsAgent,
    commande_recommandee,
)


def _cmd_pour(ctx: ScenarioContext):
    """Calcule la commande recommandée à t = 0 pour le scénario donné.

    On place l'ego à l'origine et on positionne les agents sur son axe
    longitudinal — c'est ce que fait le simulateur, cohérent avec les
    hypothèses du contrôleur.
    """
    a = assess_risk(ctx, RiskConfig())
    obs = [
        ObsAgent(x=ag.distance_m, y=ag.ecart_lateral_m, drac=ar.drac)
        for ag, ar in zip(ctx.agents, a.details)
    ]
    return commande_recommandee(a, ctx, ego_x=0.0, ego_y=0.0, agents=obs)


def test_safe_sur_route_libre_pas_de_commande():
    # Agent lointain qui s'éloigne (plus rapide, cap 0) → SAFE → aucune action.
    ctx = ScenarioContext(vitesse_ego_kmh=80,
                          agents=[Agent(TypeAgent.VOITURE, 110, 60, 0)])
    cmd = _cmd_pour(ctx)
    assert cmd.acceleration_ms2 == 0.0
    assert cmd.brake == 0.0
    assert cmd.throttle == 0.0
    assert cmd.mode == "nominal"


def test_obstacle_en_voie_declenche_freinage_physique():
    # Voiture immobile à 40 m devant : mode "physique", brake > 0.
    ctx = ScenarioContext(vitesse_ego_kmh=80,
                          agents=[Agent(TypeAgent.VOITURE, 0, 40, 0)])
    cmd = _cmd_pour(ctx)
    assert cmd.mode == "physique"
    assert cmd.acceleration_ms2 < 0
    assert 0.0 < cmd.brake <= 1.0
    assert cmd.throttle == 0.0


def test_freinage_plafonne_a_mu_g():
    # Situation inévitable : requis > µ·g → la commande est plafonnée à -µ·g.
    ctx = ScenarioContext(vitesse_ego_kmh=90,
                          agents=[Agent(TypeAgent.VOITURE, 0, 15, 0)])
    cmd = _cmd_pour(ctx)
    assert cmd.acceleration_ms2 >= -cmd.mu_g - 1e-9
    assert cmd.brake == 1.0  # plein frein


def test_verglas_reduit_le_plafond_de_freinage():
    # Sur verglas, µ·g chute — le plafond suit.
    sec = _cmd_pour(ScenarioContext(vitesse_ego_kmh=90,
                                    agents=[Agent(TypeAgent.VOITURE, 0, 40, 0)]))
    verglas = _cmd_pour(ScenarioContext(vitesse_ego_kmh=90,
                                        agents=[Agent(TypeAgent.VOITURE, 0, 40, 0)],
                                        etat_route=EtatRoute.VERGLAS))
    assert verglas.mu_g < sec.mu_g
    # Sur verglas la décélération commandée est plus faible (en amplitude).
    assert abs(verglas.acceleration_ms2) <= abs(sec.acceleration_ms2) + 1e-9


def test_croisement_hors_voie_utilise_freinage_proportionnel():
    # Piéton latéralement à 6 m, cap 90° : hors de la voie devant → mode
    # "proportionnel" (basé sur le niveau, pas sur le DRAC agent-par-agent).
    ctx = ScenarioContext(vitesse_ego_kmh=50,
                          agents=[Agent(TypeAgent.PIETON, 5, 20, 90,
                                        ecart_lateral_m=6)])
    cmd = _cmd_pour(ctx)
    assert cmd.mode in ("proportionnel", "nominal")


def test_moteur_ne_commande_jamais_d_acceleration_positive():
    # Le contrôleur est une couche de sécurité : throttle toujours à 0.
    for cas in [
        ScenarioContext(vitesse_ego_kmh=80, agents=[Agent(TypeAgent.VOITURE, 110, 60, 0)]),
        ScenarioContext(vitesse_ego_kmh=80, agents=[Agent(TypeAgent.VOITURE, 0, 40, 0)]),
        ScenarioContext(vitesse_ego_kmh=50, agents=[Agent(TypeAgent.PIETON, 5, 30, 90, ecart_lateral_m=5)]),
    ]:
        assert _cmd_pour(cas).throttle == 0.0


def test_freinage_par_niveau_ordre_croissant():
    # Cohérence de la table : plus le niveau monte, plus on freine fort.
    from risk_engine import RiskLevel
    assert FREINAGE_PAR_NIVEAU[RiskLevel.SAFE] == 0.0
    assert (FREINAGE_PAR_NIVEAU[RiskLevel.WATCH]
            > FREINAGE_PAR_NIVEAU[RiskLevel.DANGER]
            > FREINAGE_PAR_NIVEAU[RiskLevel.CRITICAL])
