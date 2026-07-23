from risk_engine import Agent, RiskLevel, ScenarioContext, TypeAgent
from sim import collision, run


def _ctx_rapprochement():
    # ego 80 rattrape une voiture à 30 km/h, 40 m devant, même sens
    return ScenarioContext(
        vitesse_ego_kmh=80,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=30, distance_m=40, cap_relatif_deg=0)],
    )


def test_le_risque_escalade_sans_reaction():
    # Départ plus lointain (120 m) pour partir d'un état peu risqué et monter
    ctx = ScenarioContext(
        vitesse_ego_kmh=80,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=30, distance_m=120, cap_relatif_deg=0)],
    )
    frames = run(ctx, reaction=False)
    niveaux = [f.assessment.level for f in frames]
    # le scénario commence moins risqué qu'il ne finit
    assert niveaux[0] < niveaux[-1]
    # et il finit par une collision si l'ego ne réagit pas
    assert collision(frames)


def test_la_reaction_evite_la_collision():
    frames = run(_ctx_rapprochement(), reaction=True)
    assert not collision(frames)


def test_distance_decroit_puis_se_stabilise_avec_reaction():
    frames = run(_ctx_rapprochement(), reaction=True)
    dmin = min(min(((s.x - f.ego.x) ** 2) ** 0.5 for s in f.agents) for f in frames)
    assert dmin > 1.5  # n'a jamais atteint la distance de collision


def test_scenario_sur_emis_reste_safe():
    # agent loin et lent dans le même sens -> reste SAFE un moment
    ctx = ScenarioContext(
        vitesse_ego_kmh=50,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=48, distance_m=120, cap_relatif_deg=0)],
    )
    frames = run(ctx, reaction=False, t_max=2.0)
    assert frames[0].assessment.level == RiskLevel.SAFE


def test_freinage_plafonne_par_adherence():
    # Sur verglas, l'ego ne peut pas freiner plus fort que µ·g (≈2.9 m/s²),
    # même si le niveau CRITICAL « voudrait » -8 m/s².
    from risk_engine.context import EtatRoute
    from risk_engine import modifiers, metrics
    ctx = ScenarioContext(
        vitesse_ego_kmh=70, etat_route=EtatRoute.VERGLAS,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=0, distance_m=35, cap_relatif_deg=0)],
    )
    frames = run(ctx, reaction=True)
    a_max = modifiers.mu(EtatRoute.VERGLAS) * metrics.G
    assert all(f.ego_accel >= -a_max - 1e-9 for f in frames)   # jamais au-delà de l'adhérence
    assert min(f.ego_accel for f in frames) > -8.0             # le plafond mord bien


def test_ecart_lateral_traversee():
    # Un agent décalé latéralement et en croisement (cap 90) est placé à sa
    # VRAIE distance et se dirige vers l'axe de l'ego : |y| passe par ~0 (traversée).
    import math
    ctx = ScenarioContext(
        vitesse_ego_kmh=50,
        agents=[Agent(TypeAgent.PIETON, vitesse_kmh=5, distance_m=20,
                      cap_relatif_deg=90, ecart_lateral_m=6.0)],
    )
    frames = run(ctx, reaction=False)
    s0 = frames[0].agents[0]
    assert abs(math.hypot(s0.x, s0.y) - 20.0) < 0.1   # vraie distance initiale = 20 m
    assert s0.y == 6.0                                 # départ décalé
    assert min(abs(f.agents[0].y) for f in frames) < 0.5   # traverse l'axe


def test_arret_complet_obstacle_en_voie():
    # Obstacle immobile dans la voie : le freinage d'urgence différencié doit
    # amener l'ego à l'arrêt complet (et non à une vitesse résiduelle).
    ctx = ScenarioContext(
        vitesse_ego_kmh=90,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=0, distance_m=40, cap_relatif_deg=0)],
    )
    frames = run(ctx, reaction=True)
    assert frames[-1].ego.speed_ms < 0.2  # ~ 0 km/h


def test_diagnostic_collision_inevitable():
    # Obstacle trop proche pour l'adhérence : collision inévitable, signalée comme telle.
    from sim import diagnostic_collision
    ctx = ScenarioContext(
        vitesse_ego_kmh=80,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=0, distance_m=20, cap_relatif_deg=0)],
    )
    diag = diagnostic_collision(run(ctx, reaction=True), ctx)
    assert "INÉVITABLE" in diag


def test_collision_evitable_est_evitee():
    # Obstacle à distance suffisante : le freinage physique l'évite.
    from sim import collision
    ctx = ScenarioContext(
        vitesse_ego_kmh=80,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=0, distance_m=40, cap_relatif_deg=0)],
    )
    assert not collision(run(ctx, reaction=True))
