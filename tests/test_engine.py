from risk_engine import (
    Agent,
    EtatRoute,
    RiskLevel,
    ScenarioContext,
    TypeAgent,
    assess_risk,
)


def test_safe_lointain():
    ctx = ScenarioContext(
        vitesse_ego_kmh=50,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=45, distance_m=100, cap_relatif_deg=0)],
    )
    assert assess_risk(ctx).level == RiskLevel.SAFE


def test_critical_obstacle_proche():
    # ego 90, voiture arrêtée à 15 m, même sens, route sèche
    ctx = ScenarioContext(
        vitesse_ego_kmh=90,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=0, distance_m=15, cap_relatif_deg=0)],
    )
    assert assess_risk(ctx).level == RiskLevel.CRITICAL


def test_sc02_freinage_brusque():
    # SC-02 : ego 90, leader lent à 40 m, même sens
    ctx = ScenarioContext(
        vitesse_ego_kmh=90,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=30, distance_m=40, cap_relatif_deg=0)],
    )
    assert assess_risk(ctx).level >= RiskLevel.DANGER


def test_friction_escalade():
    # Même situation, sec vs verglas : le verglas doit aggraver le niveau
    agent = lambda: Agent(TypeAgent.VOITURE, vitesse_kmh=20, distance_m=40, cap_relatif_deg=0)
    sec = assess_risk(ScenarioContext(vitesse_ego_kmh=50, etat_route=EtatRoute.SEC, agents=[agent()]))
    verglas = assess_risk(
        ScenarioContext(vitesse_ego_kmh=50, etat_route=EtatRoute.VERGLAS, agents=[agent()])
    )
    assert verglas.level > sec.level


def test_vru_plus_conservateur():
    # Croisement identique : piéton plus à risque qu'une voiture
    def ctx(t):
        return ScenarioContext(
            vitesse_ego_kmh=50,
            agents=[Agent(t, vitesse_kmh=5, distance_m=30, cap_relatif_deg=90)],
        )

    voiture = assess_risk(ctx(TypeAgent.VOITURE))
    pieton = assess_risk(ctx(TypeAgent.PIETON))
    assert pieton.level > voiture.level


def test_multi_agents_pire_cas():
    # Un agent bénin lointain + un piéton à risque -> niveau = pire, agent critique = piéton
    ctx = ScenarioContext(
        vitesse_ego_kmh=50,
        agents=[
            Agent(TypeAgent.VOITURE, vitesse_kmh=48, distance_m=150, cap_relatif_deg=0),
            Agent(TypeAgent.PIETON, vitesse_kmh=5, distance_m=30, cap_relatif_deg=90),
        ],
    )
    r = assess_risk(ctx)
    assert r.level >= RiskLevel.DANGER
    assert r.agent_critique.type_agent == TypeAgent.PIETON


def test_incertitude_profondeur():
    # Profondeur inférée (caméra) -> marge accrue -> niveau >= profondeur mesurée
    def ctx(mesuree):
        return ScenarioContext(
            vitesse_ego_kmh=70,
            agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=40, distance_m=45,
                          cap_relatif_deg=0, profondeur_mesuree=mesuree)],
        )

    mesuree = assess_risk(ctx(True))
    inferee = assess_risk(ctx(False))
    assert inferee.level >= mesuree.level
