"""Invariants du moteur (property-checks) : propriétés qui doivent tenir
quelles que soient les évolutions de seuils, poids ou filtrage."""
import math

from risk_engine import Agent, RiskLevel, ScenarioContext, TypeAgent, assess_risk
from risk_engine.context import EtatRoute, Heure, Meteo


def _niv(ctx):
    return assess_risk(ctx).level


def _ctx(**kw):
    d = dict(vitesse_ego_kmh=80)
    d.update(kw)
    return ScenarioContext(**d)


def test_monotonie_distance():
    # Plus l'obstacle est proche, plus le niveau est élevé (jamais l'inverse).
    niveaux = [_niv(_ctx(agents=[Agent(TypeAgent.VOITURE, 0, d, 0)]))
               for d in [150, 100, 60, 40, 25, 12]]
    assert all(int(niveaux[i + 1]) >= int(niveaux[i]) for i in range(len(niveaux) - 1))


def test_friction_degradee_plus_severe():
    sec = _niv(_ctx(agents=[Agent(TypeAgent.VOITURE, 0, 45, 0)], etat_route=EtatRoute.SEC))
    verglas = _niv(_ctx(agents=[Agent(TypeAgent.VOITURE, 0, 45, 0)],
                        etat_route=EtatRoute.VERGLAS, meteo=Meteo.NEIGE))
    assert int(verglas) >= int(sec)


def test_vru_plus_severe_que_motorise():
    voiture = _niv(_ctx(vitesse_ego_kmh=50, agents=[Agent(TypeAgent.VOITURE, 5, 15, 0)]))
    pieton = _niv(_ctx(vitesse_ego_kmh=50, agents=[Agent(TypeAgent.PIETON, 5, 15, 0)]))
    assert int(pieton) >= int(voiture)


def test_global_est_le_max_des_agents():
    a = assess_risk(_ctx(agents=[Agent(TypeAgent.VOITURE, 60, 120, 0),
                                 Agent(TypeAgent.PIETON, 5, 18, 0)]))
    assert a.level == max(d.level for d in a.details)


def test_filtrage_lateral_jamais_amplifiant():
    axe = _niv(_ctx(agents=[Agent(TypeAgent.VOITURE, 30, 40, 0, ecart_lateral_m=0)]))
    loin = _niv(_ctx(agents=[Agent(TypeAgent.VOITURE, 30, 40, 0, ecart_lateral_m=12)]))
    assert int(loin) <= int(axe)


def test_agent_qui_s_eloigne_est_safe():
    assert _niv(_ctx(agents=[Agent(TypeAgent.VOITURE, 110, 60, 0)])) == RiskLevel.SAFE


def test_nan_tolere_par_sanitize():
    n = _niv(_ctx(agents=[Agent(TypeAgent.VOITURE, float("nan"), 40, 0)]))
    assert n in list(RiskLevel)


def test_profondeur_inferee_plus_severe():
    mesuree = _niv(_ctx(vitesse_ego_kmh=70,
                        agents=[Agent(TypeAgent.VOITURE, 20, 35, 0, profondeur_mesuree=True)]))
    inferee = _niv(_ctx(vitesse_ego_kmh=70,
                        agents=[Agent(TypeAgent.VOITURE, 20, 35, 0, profondeur_mesuree=False)]))
    assert int(inferee) >= int(mesuree)


def test_nuit_visibilite_plus_severe():
    jour = _niv(_ctx(vitesse_ego_kmh=60, agents=[Agent(TypeAgent.PIETON, 5, 20, 0)]))
    nuit = _niv(_ctx(vitesse_ego_kmh=60, agents=[Agent(TypeAgent.PIETON, 5, 20, 0)],
                     heure=Heure.NUIT, visibilite_m=30))
    assert int(nuit) >= int(jour)


def test_obstacle_inevitable_est_critical():
    assert _niv(_ctx(vitesse_ego_kmh=90,
                     agents=[Agent(TypeAgent.VOITURE, 0, 15, 0)])) == RiskLevel.CRITICAL
