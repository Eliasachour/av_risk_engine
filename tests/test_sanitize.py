"""Tests de la couche d'assainissement (borner + avertir)."""
import math

from risk_engine import Agent, ScenarioContext, TypeAgent
from risk_engine.sanitize import sanitize_context, VITESSE_MAX_KMH, ACCEL_MAX_MS2


def _ctx(agent):
    return ScenarioContext(vitesse_ego_kmh=80, agents=[agent])


def test_vitesse_excessive_bornee():
    ctx, av = sanitize_context(_ctx(Agent(TypeAgent.VOITURE, 9999, 40, 0)))
    assert ctx.agents[0].vitesse_kmh == VITESSE_MAX_KMH
    assert any("vitesse" in w for w in av)


def test_acceleration_excessive_bornee():
    ctx, av = sanitize_context(_ctx(Agent(TypeAgent.VOITURE, 50, 40, 0, acceleration_ms2=999)))
    assert ctx.agents[0].acceleration_ms2 == ACCEL_MAX_MS2


def test_cap_replie_sur_0_180():
    ctx, _ = sanitize_context(_ctx(Agent(TypeAgent.VOITURE, 50, 40, 270)))
    assert ctx.agents[0].cap_relatif_deg == 90.0


def test_nan_remplace():
    ctx, av = sanitize_context(_ctx(Agent(TypeAgent.VOITURE, 50, float("nan"), 0)))
    assert math.isfinite(ctx.agents[0].distance_m)
    assert av  # une correction a été signalée


def test_valeurs_valides_inchangees():
    ctx, av = sanitize_context(_ctx(Agent(TypeAgent.VOITURE, 50, 40, 90)))
    assert av == []
    assert ctx.agents[0].vitesse_kmh == 50
