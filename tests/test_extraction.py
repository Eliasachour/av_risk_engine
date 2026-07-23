import math

from risk_engine.context import Meteo, ScenarioContext, TypeAgent
from world.extraction import (
    ActorState,
    AgentObservation,
    planar_distance,
    refresh_context,
    relative_heading_deg,
)


def test_distance_plane():
    a = ActorState(0, 0, 0, 0)
    b = ActorState(3, 4, 0, 0)
    assert math.isclose(planar_distance(a, b), 5.0)


def test_cap_meme_sens():
    assert relative_heading_deg(0, 0) == 0


def test_cap_face_a_face():
    assert relative_heading_deg(0, 180) == 180


def test_cap_croisement():
    assert relative_heading_deg(0, 90) == 90


def test_cap_wrap_autour_de_360():
    # 350° vs 10° -> écart réel de 20°
    assert math.isclose(relative_heading_deg(350, 10), 20.0)


def test_refresh_context_construit_agents():
    base = ScenarioContext(vitesse_ego_kmh=0, meteo=Meteo.CLAIR)
    ego = ActorState(x=0, y=0, yaw_deg=0, speed_ms=25.0)            # 90 km/h
    obs = AgentObservation(
        state=ActorState(x=40, y=0, yaw_deg=180, speed_ms=8.333),   # face-à-face, 30 km/h
        type_agent=TypeAgent.VOITURE,
    )
    ctx = refresh_context(base, ego, [obs])

    assert math.isclose(ctx.vitesse_ego_kmh, 90.0, abs_tol=0.5)
    assert len(ctx.agents) == 1
    ag = ctx.agents[0]
    assert math.isclose(ag.distance_m, 40.0)
    assert math.isclose(ag.cap_relatif_deg, 180.0)
    assert math.isclose(ag.vitesse_kmh, 30.0, abs_tol=0.5)
    # les champs d'environnement du contexte de base sont préservés
    assert ctx.meteo == Meteo.CLAIR
