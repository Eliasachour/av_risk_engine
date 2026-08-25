"""Tests des composants du mode conduite libre.

- La machine à états `Assistance` (eval / alerte / aeb) et son comportement
  attendu selon la persistance CRITICAL.
- La classification blueprint → TypeAgent utilisée par la perception oracle.

Ces tests n'ont pas besoin de CARLA ni de Pygame — ils vérifient la logique
pure, ce qui est justement l'intérêt d'avoir isolé ces briques dans leur
propre module.
"""
from risk_engine import RiskLevel, TypeAgent
from world.aeb import Assistance
from world.perception_oracle import type_agent_depuis_blueprint


# ---------------------------------------------------------------------------
# Classification blueprint
# ---------------------------------------------------------------------------


def test_blueprint_voiture():
    assert type_agent_depuis_blueprint("vehicle.tesla.model3") == TypeAgent.VOITURE
    assert type_agent_depuis_blueprint("vehicle.audi.a2") == TypeAgent.VOITURE


def test_blueprint_camion():
    # firetruck, sprinter → CAMION
    assert type_agent_depuis_blueprint("vehicle.carlamotors.firetruck") == TypeAgent.CAMION
    assert type_agent_depuis_blueprint("vehicle.mercedes.sprinter") == TypeAgent.CAMION


def test_blueprint_pieton():
    assert type_agent_depuis_blueprint("walker.pedestrian.0001") == TypeAgent.PIETON
    assert type_agent_depuis_blueprint("walker.pedestrian.0003") == TypeAgent.PIETON


def test_blueprint_ouvrier():
    # Certains ids correspondent a des tenues de type "ouvrier"
    assert type_agent_depuis_blueprint("walker.pedestrian.0002") == TypeAgent.OUVRIER
    assert type_agent_depuis_blueprint("walker.pedestrian.0004") == TypeAgent.OUVRIER


def test_blueprint_cycliste():
    assert type_agent_depuis_blueprint("vehicle.bh.crossbike") == TypeAgent.CYCLISTE
    assert type_agent_depuis_blueprint("vehicle.diamondback.century") == TypeAgent.CYCLISTE


def test_blueprint_ignore_sensors_et_static():
    # Ce qui n'est ni vehicle. ni walker.pedestrian. → None (on l'ignore)
    assert type_agent_depuis_blueprint("sensor.camera.rgb") is None
    assert type_agent_depuis_blueprint("static.prop.streetsign") is None
    assert type_agent_depuis_blueprint("controller.ai.walker") is None


# ---------------------------------------------------------------------------
# Machine à états Assistance
# ---------------------------------------------------------------------------


def test_mode_eval_n_intervient_jamais():
    """En mode eval, meme un CRITICAL persistant ne declenche rien."""
    a = Assistance(mode="eval")
    for t in [0.0, 0.5, 1.0, 2.0]:
        d = a.decider(RiskLevel.CRITICAL, t)
        assert not d.override_brake
        assert not d.alerte_active


def test_mode_alerte_active_en_danger():
    """En mode alerte, DANGER active l'alerte visuelle (mais pas d'AEB)."""
    a = Assistance(mode="alerte")
    d = a.decider(RiskLevel.DANGER, 0.0)
    assert d.alerte_active
    assert not d.alerte_critical
    assert not d.override_brake


def test_mode_alerte_marque_critical():
    """En mode alerte, CRITICAL est signale differemment (pour pulsation)."""
    a = Assistance(mode="alerte")
    d = a.decider(RiskLevel.CRITICAL, 0.0)
    assert d.alerte_active
    assert d.alerte_critical


def test_mode_alerte_reste_active_apres_baisse():
    """Une fois l'alerte declenchee, elle reste visible >= duree_alerte_min."""
    a = Assistance(mode="alerte", duree_alerte_min=1.0)
    a.decider(RiskLevel.DANGER, 0.0)
    d = a.decider(RiskLevel.SAFE, 0.5)   # niveau redescend
    assert d.alerte_active, "l'alerte doit persister au moins duree_alerte_min"
    d = a.decider(RiskLevel.SAFE, 1.5)   # apres duree_alerte_min
    assert not d.alerte_active


def test_mode_aeb_n_engage_pas_sur_critical_ponctuel():
    """Un CRITICAL d'un seul tick ne doit pas engager l'AEB (artefacts)."""
    a = Assistance(mode="aeb", duree_critical_avant_aeb=0.4)
    d = a.decider(RiskLevel.CRITICAL, 0.0)
    assert not d.override_brake
    # Retour a SAFE tout de suite
    d = a.decider(RiskLevel.SAFE, 0.05)
    assert not d.override_brake


def test_mode_aeb_engage_apres_persistance():
    """CRITICAL persistant > seuil temporel → AEB engage."""
    a = Assistance(mode="aeb", duree_critical_avant_aeb=0.4)
    a.decider(RiskLevel.CRITICAL, 0.0)
    a.decider(RiskLevel.CRITICAL, 0.2)
    d = a.decider(RiskLevel.CRITICAL, 0.5)   # 0.5 s de CRITICAL persistant
    assert d.override_brake
    assert d.override_brake_valeur == 1.0


def test_mode_aeb_ne_double_pas_le_conducteur():
    """Si le conducteur freine deja, AEB ne se declenche pas."""
    a = Assistance(mode="aeb", duree_critical_avant_aeb=0.4)
    a.decider(RiskLevel.CRITICAL, 0.0, conducteur_freine=True)
    a.decider(RiskLevel.CRITICAL, 0.2, conducteur_freine=True)
    d = a.decider(RiskLevel.CRITICAL, 0.5, conducteur_freine=True)
    assert not d.override_brake


def test_mode_aeb_reprise_conducteur_desengage():
    """Le conducteur qui reappuie sur l'accelerateur reprend le controle."""
    a = Assistance(mode="aeb", duree_critical_avant_aeb=0.4)
    a.decider(RiskLevel.CRITICAL, 0.0)
    a.decider(RiskLevel.CRITICAL, 0.2)
    d = a.decider(RiskLevel.CRITICAL, 0.5)
    assert d.override_brake
    # Le conducteur accelere pour reprendre
    d = a.decider(RiskLevel.CRITICAL, 0.6, conducteur_accelere=True)
    assert not d.override_brake, "acceleration explicite doit desengager l'AEB"


def test_statut_court():
    assert Assistance(mode="eval").statut_court() == "EVAL"
    assert Assistance(mode="alerte").statut_court() == "ALERTE"
    assert Assistance(mode="aeb").statut_court() == "AEB"
