"""
Tests d'intégration CARLA — exécutés contre le double de test.

Ces tests ne valident pas la physique (le double n'en a quasiment pas). Ils
valident **les signatures et l'enchaînement des appels**, c'est-à-dire
exactement la classe d'erreurs qui est passée en production faute de serveur
CARLA sous la main :

- ``TrafficManager.get_synchronous_mode`` — méthode inexistante ;
- ``to_carla_weather`` — fonction mal nommée (le vrai nom est ``weather_params``) ;
- ``contexte_courant()`` appelé sans argument alors qu'il en exigeait un ;
- absence de ``tick()`` entre le spawn de l'ego et celui du trafic, qui faisait
  lire une position (0, 0, 0) et spawner zéro véhicule.

Chacune de ces quatre erreurs aurait été détectée ici en une seconde. C'est la
raison d'être de ce fichier.
"""
import math

import pytest

from risk_engine import RiskLevel, TypeAgent, assess_risk
from tests.fake_carla import installer


@pytest.fixture(autouse=True)
def _carla_factice():
    """Installe le faux module `carla` avant chaque test de ce fichier."""
    installer()
    yield


# ---------------------------------------------------------------------------
# Le pont de perception
# ---------------------------------------------------------------------------


def test_pont_cycle_de_vie_complet():
    """Connexion, carte, scénario, ticks, contexte, nettoyage."""
    from calibration import REFERENCES
    from world.carla_bridge import CarlaBridge

    ref = REFERENCES[0]
    with CarlaBridge(fixed_delta_seconds=0.05) as pont:
        pont.charger_carte("Town04")
        pont.appliquer_scenario(ref.ctx)
        assert pont.ego is not None

        for _ in range(5):
            pont.tick()
            # Appelé SANS argument : c'est le bug qui a cassé le rejeu.
            ctx = pont.contexte_courant()
            assert ctx.vitesse_ego_kmh >= 0.0
            niveau = assess_risk(ctx).level
            assert niveau in list(RiskLevel)

    # Après sortie du context manager, les acteurs sont détruits.
    assert pont.ego is None


def test_contexte_courant_accepte_un_contexte_explicite():
    """Le mode conduite libre passe un contexte à jour (la météo change)."""
    from dataclasses import replace

    from calibration import REFERENCES
    from risk_engine.context import EtatRoute, Meteo
    from world.carla_bridge import CarlaBridge

    ref = REFERENCES[0]
    with CarlaBridge() as pont:
        pont.charger_carte("Town04")
        pont.appliquer_scenario(ref.ctx)
        pont.tick()

        ctx_neige = replace(ref.ctx, meteo=Meteo.NEIGE,
                            etat_route=EtatRoute.VERGLAS)
        ctx = pont.contexte_courant(ctx_neige)
        assert ctx.etat_route is EtatRoute.VERGLAS


def test_weather_params_est_le_bon_nom():
    """`to_carla_weather` n'existe pas ; le nom correct est `weather_params`."""
    import carla

    from calibration import REFERENCES
    from world import weather

    assert not hasattr(weather, "to_carla_weather")
    params = weather.weather_params(REFERENCES[0].ctx)
    # Le dictionnaire doit être directement dépliable dans WeatherParameters.
    w = carla.WeatherParameters(**params)
    assert hasattr(w, "precipitation")


def test_traffic_manager_n_a_pas_de_getter_synchrone():
    """Documente l'absence de `get_synchronous_mode` côté API CARLA.

    Si ce test échoue un jour, c'est que l'API a gagné un getter et que le pont
    peut restaurer l'état d'origine au lieu de forcer le mode asynchrone.
    """
    import carla

    tm = carla.Client("localhost", 2000).get_trafficmanager()
    assert hasattr(tm, "set_synchronous_mode")
    assert not hasattr(tm, "get_synchronous_mode")


# ---------------------------------------------------------------------------
# Le trafic
# ---------------------------------------------------------------------------


def test_trafic_spawne_avec_un_centre_explicite():
    """Le spawn du trafic exige une position de référence utilisable.

    Sans `centre`, en mode synchrone et sans tick préalable,
    `ego.get_transform()` renvoie l'instantané précédent — soit (0, 0, 0) — et
    le filtrage par distance élimine tous les points de spawn de la carte.
    C'est le bug des « 0 véhicules IA spawn ».
    """
    from calibration import REFERENCES
    from world.carla_bridge import CarlaBridge
    from world.traffic import GestionnaireTrafic

    with CarlaBridge() as pont:
        pont.charger_carte("Town04")
        pont.appliquer_scenario(REFERENCES[0].ctx)
        pont.tick()

        centre = pont.ego.get_transform().location
        with GestionnaireTrafic(pont.world, pont.tm,
                               n_vehicules=5, n_pietons=3) as trafic:
            trafic.spawn_autour_de(pont.ego, rayon_m=200.0, centre=centre)
            assert len(trafic.vehicules) > 0, (
                "aucun véhicule spawné : vérifier le filtrage par distance"
            )
        # Nettoyage effectif à la sortie.
        assert trafic.vehicules == []


# ---------------------------------------------------------------------------
# Les capteurs d'environnement
# ---------------------------------------------------------------------------


def test_capteurs_environnement_se_montent_et_se_detruisent():
    from calibration import REFERENCES
    from world.carla_bridge import CarlaBridge
    from world.env_sensors import (
        DetecteurCollision, DetecteurObstacle, contexte_route,
    )

    with CarlaBridge() as pont:
        pont.charger_carte("Town04")
        pont.appliquer_scenario(REFERENCES[0].ctx)
        pont.tick()

        obs = DetecteurObstacle(pont.world, pont.ego, portee_m=60.0)
        coll = DetecteurCollision(pont.world, pont.ego)
        for i in range(5):
            pont.tick()
            obs.maj_temps(i * 0.05)
            coll.maj_temps(i * 0.05)

        cr = contexte_route(pont.world, pont.ego)
        assert cr.limite_vitesse_kmh > 0
        assert cr.feu in ("rouge", "jaune", "vert", "aucun")
        assert coll.nombre >= 0

        obs.detruire()
        coll.detruire()


def test_obstacle_statique_devient_un_agent_immobile():
    """Un mur détecté doit se traduire en `Agent` de vitesse nulle."""
    from world.env_sensors import DetecteurObstacle, InfoObstacle

    det = DetecteurObstacle.__new__(DetecteurObstacle)   # sans spawn
    det.sensor = None
    det._t_courant = 1.0
    det.info = InfoObstacle(distance_m=18.0, est_statique=True,
                            etiquette="static.prop.wall", t_detection=1.0)

    ag = det.agent_equivalent()
    assert ag is not None
    assert ag.vitesse_kmh == 0.0
    assert ag.distance_m == pytest.approx(18.0)
    assert ag.cap_relatif_deg == 0.0
    assert ag.ecart_lateral_m == 0.0


def test_detection_obstacle_se_perime():
    """Le capteur ne signale rien quand la voie est libre : la détection
    doit se périmer, sinon on garderait un mur qui n'existe plus."""
    from world.env_sensors import DetecteurObstacle, InfoObstacle

    det = DetecteurObstacle.__new__(DetecteurObstacle)
    det.sensor = None
    det.info = InfoObstacle(distance_m=18.0, est_statique=True, t_detection=1.0)

    det._t_courant = 1.2
    assert det.agent_equivalent() is not None      # frais
    det._t_courant = 3.0
    assert det.agent_equivalent() is None          # périmé


# ---------------------------------------------------------------------------
# La météo en direct
# ---------------------------------------------------------------------------


def test_meteo_preset_neige_durcit_le_verdict():
    """Passer en neige/verglas doit faire chuter µ·g et durcir l'évaluation.

    C'est la démonstration de la décision D14 rendue interactive : le même
    conflit devient plus grave parce que l'adhérence disponible s'effondre.
    """
    from risk_engine import Agent, ScenarioContext, TypeAgent, metrics, modifiers
    from world.hud.weather_control import PRESETS, ControleMeteo

    class MondeFactice:
        def set_weather(self, w):
            self.w = w

    ctx = ScenarioContext(
        vitesse_ego_kmh=90,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=80, distance_m=70,
                      cap_relatif_deg=0)],
    )
    m = ControleMeteo(MondeFactice(), ctx)

    i_clair = next(i for i, p in enumerate(PRESETS) if p.nom == "Clair")
    i_neige = next(i for i, p in enumerate(PRESETS) if "Neige" in p.nom)

    m._charger_preset(i_clair)
    niveau_clair = assess_risk(m.contexte()).level
    mu_clair = modifiers.mu(m.contexte().etat_route) * metrics.G

    m._charger_preset(i_neige)
    niveau_neige = assess_risk(m.contexte()).level
    mu_neige = modifiers.mu(m.contexte().etat_route) * metrics.G

    assert mu_neige < mu_clair, "l'adhérence doit chuter sur verglas"
    assert int(niveau_neige) >= int(niveau_clair), (
        "le même conflit ne peut pas devenir moins grave sur sol dégradé"
    )


def test_meteo_synchronise_la_friction_des_pneus():
    """La friction simulée doit suivre l'état de route vu par le moteur.

    Sans cela, la météo CARLA reste purement visuelle : sur verglas le véhicule
    freinerait encore comme sur sol sec alors que le moteur suppose
    µ·g ≈ 2,9 m/s². Le simulé et l'évalué divergeraient.
    """
    from calibration import REFERENCES
    from world.carla_bridge import CarlaBridge
    from world.hud.weather_control import PRESETS, ControleMeteo

    with CarlaBridge() as pont:
        pont.charger_carte("Town04")
        pont.appliquer_scenario(REFERENCES[0].ctx)
        pont.tick()

        m = ControleMeteo(pont.world, REFERENCES[0].ctx)
        i_neige = next(i for i, p in enumerate(PRESETS) if "Neige" in p.nom)
        m._charger_preset(i_neige)

        ratio = m.appliquer_friction(pont.ego)
        assert ratio is not None, "l'application de la friction a échoué"
        assert ratio < 1.0, "la friction doit être réduite sur verglas"


# ---------------------------------------------------------------------------
# Écart latéral et scènes urbaines réalistes
# ---------------------------------------------------------------------------


def test_ecart_lateral_est_calcule_depuis_les_poses():
    """L'écart latéral doit être renseigné par la conversion CARLA → moteur.

    C'était le bug majeur du mode conduite libre : `agent_from_observation`
    n'alimentait pas `ecart_lateral_m`, donc tout agent perçu arrivait avec un
    écart nul — c'est-à-dire considéré comme étant dans la voie de l'ego. Le
    filtrage latéral (D8) ne pouvait jamais s'activer.
    """
    from risk_engine import ScenarioContext
    from world.extraction import ActorState, AgentObservation, refresh_context

    ego = ActorState(x=0, y=0, yaw_deg=0, speed_ms=13.9)
    a_droite = ActorState(x=30, y=6.0, yaw_deg=0, speed_ms=0)
    ctx = refresh_context(
        ScenarioContext(vitesse_ego_kmh=50, agents=[]),
        ego,
        [AgentObservation(a_droite, TypeAgent.VOITURE, True)],
    )
    assert ctx.agents[0].ecart_lateral_m == pytest.approx(6.0, abs=0.1)


def test_ecart_lateral_correct_avec_ego_oriente():
    """La projection doit rester juste quel que soit le cap de l'ego."""
    from world.extraction import ActorState, ecart_lateral_m

    ego = ActorState(x=0, y=0, yaw_deg=45, speed_ms=10)
    # Agent placé exactement dans l'axe de l'ego (45°) : écart nul.
    dans_axe = ActorState(x=40 * math.cos(math.radians(45)),
                          y=40 * math.sin(math.radians(45)),
                          yaw_deg=45, speed_ms=0)
    assert ecart_lateral_m(ego, dans_axe) == pytest.approx(0.0, abs=0.01)


def test_vehicule_gare_sur_le_bas_cote_est_safe():
    """Une voiture garée à 6 m de l'axe ne doit pas alarmer le moteur."""
    from risk_engine import ScenarioContext
    from world.extraction import ActorState, AgentObservation, refresh_context

    ego = ActorState(x=0, y=0, yaw_deg=0, speed_ms=13.9)
    gare = ActorState(x=25, y=6.0, yaw_deg=0, speed_ms=0)
    ctx = refresh_context(
        ScenarioContext(vitesse_ego_kmh=50, agents=[]),
        ego, [AgentObservation(gare, TypeAgent.VOITURE, True)])
    assert assess_risk(ctx).level == RiskLevel.SAFE


def test_pieton_qui_longe_le_trottoir_est_safe():
    """Un piéton marchant PARALLÈLEMENT à la route n'est pas un conflit.

    Le moteur ne rétrograde jamais un VRU qui traverse (garantie de sécurité,
    voir SC-21). Mais un VRU qui longe la route n'est pas sur une trajectoire
    de collision : sans cette distinction, tout trottoir peuplé produisait un
    DANGER permanent en conduite libre.
    """
    from risk_engine import ScenarioContext
    from world.extraction import ActorState, AgentObservation, refresh_context

    ego = ActorState(x=0, y=0, yaw_deg=0, speed_ms=13.9)
    longe = ActorState(x=20, y=7.0, yaw_deg=0, speed_ms=1.2)   # cap parallèle
    ctx = refresh_context(
        ScenarioContext(vitesse_ego_kmh=50, agents=[]),
        ego, [AgentObservation(longe, TypeAgent.PIETON, True)])
    assert assess_risk(ctx).level == RiskLevel.SAFE


def test_pieton_qui_traverse_reste_detecte():
    """Contrepartie du test précédent : la traversée doit rester détectée."""
    from risk_engine import ScenarioContext
    from world.extraction import ActorState, AgentObservation, refresh_context

    ego = ActorState(x=0, y=0, yaw_deg=0, speed_ms=13.9)
    traverse = ActorState(x=22, y=6.0, yaw_deg=-90, speed_ms=1.4)
    ctx = refresh_context(
        ScenarioContext(vitesse_ego_kmh=50, agents=[]),
        ego, [AgentObservation(traverse, TypeAgent.PIETON, True)])
    assert int(assess_risk(ctx).level) >= int(RiskLevel.WATCH)


def test_capteur_obstacle_ignore_la_chaussee():
    """Le capteur ne doit pas remonter les surfaces ni les distances nulles.

    Monté trop bas avec un rayon trop large, la capsule du capteur descendait
    sous le niveau du sol et détectait la route à chaque tick : un « obstacle
    fantôme à 0 m » permanent qui faussait toute l'évaluation.

    Le filtrage compte cinq étapes : distance crédible, surface de roulement,
    acteur déjà suivi, appartenance au couloir carrossable, et confirmation sur
    plusieurs ticks consécutifs.
    """
    from world.env_sensors import (
        DETECTIONS_AVANT_CONFIANCE, DISTANCE_MIN_CREDIBLE_M,
        DetecteurObstacle, InfoObstacle,
    )

    det = DetecteurObstacle.__new__(DetecteurObstacle)
    det.sensor = None
    det._t_courant = 1.0
    det._consecutives = 0
    det._rejets = {"proche": 0, "surface": 0, "acteur": 0, "hors_voie": 0}
    det.info = InfoObstacle()
    # Le filtre « couloir » demande la carte : on le neutralise ici pour tester
    # les quatre autres filtres isolément.
    det._dans_le_couloir = lambda distance: True

    class FauxEvenement:
        def __init__(self, type_id, distance):
            self.other_actor = type("A", (), {"type_id": type_id})()
            self.distance = distance

    # 1. Les surfaces de roulement ne sont jamais des obstacles.
    for surface in ("static.road", "Static.Sidewalk", "static.terrain",
                    "static.roadline"):
        for _ in range(DETECTIONS_AVANT_CONFIANCE + 1):
            det._on_event(FauxEvenement(surface, 12.0))
        assert det.agent_equivalent() is None, f"{surface} ne doit pas alarmer"
    assert det._rejets["surface"] > 0

    # 2. Une détection sous la distance crédible est un artefact.
    for _ in range(DETECTIONS_AVANT_CONFIANCE + 1):
        det._on_event(FauxEvenement("static.prop.streetbarrier",
                                    DISTANCE_MIN_CREDIBLE_M - 0.5))
    assert det.agent_equivalent() is None
    assert det._rejets["proche"] > 0

    # 3. Les acteurs suivis par ailleurs ne sont pas comptés deux fois.
    for _ in range(DETECTIONS_AVANT_CONFIANCE + 1):
        det._on_event(FauxEvenement("vehicle.tesla.model3", 20.0))
    assert det.agent_equivalent() is None
    assert det._rejets["acteur"] > 0

    # 4. Une détection ISOLÉE ne suffit pas : il faut confirmation.
    det._consecutives = 0
    det._on_event(FauxEvenement("static.prop.streetbarrier", 18.0))
    assert det.agent_equivalent() is None, "une détection unique ne doit pas alarmer"

    # 5. Confirmé sur plusieurs ticks : l'obstacle devient un agent immobile.
    for _ in range(DETECTIONS_AVANT_CONFIANCE):
        det._on_event(FauxEvenement("static.prop.streetbarrier", 18.0))
    ag = det.agent_equivalent()
    assert ag is not None, "un obstacle confirmé doit être transmis au moteur"
    assert ag.vitesse_kmh == 0.0
    assert ag.distance_m == pytest.approx(18.0)


# ---------------------------------------------------------------------------
# Trajet A → B
# ---------------------------------------------------------------------------


def _lancer_trajet(argv):
    """Exécute apps/carla_trajet.py avec le double CARLA et renvoie son code."""
    import runpy
    import sys as _s

    ancien = _s.argv
    try:
        _s.argv = ["carla_trajet.py"] + argv
        try:
            runpy.run_path("apps/carla_trajet.py", run_name="__main__")
        except SystemExit as e:
            return e.code or 0
        return 0
    finally:
        _s.argv = ancien


def test_trajet_route_vide_reste_safe():
    """Sur route vide, aucune alerte : c'est le test de référence.

    Toute alerte y est par construction un faux positif, puisqu'il n'y a aucun
    usager. Ce test attrape donc les régressions de la chaîne de perception —
    écart latéral, capteur d'obstacle — que les 24 scénarios scriptés ne
    peuvent pas voir, faute de décor et d'acteurs de fond.
    """
    code = _lancer_trajet(["--distance", "200", "--headless"])
    assert code == 0, (
        "des alertes sont apparues sur une route sans aucun usager : "
        "regression probable de la perception"
    )


def test_trajet_en_circulation_sans_collision():
    """Avec du trafic, l'ego doit rejoindre B sans collision.

    Ici les alertes sont normales — c'est le travail du moteur. Le critère est
    l'absence de collision, et le fait d'arriver malgré tout à destination
    (un ego qui freinerait indéfiniment échouerait aussi).
    """
    code = _lancer_trajet([
        "--distance", "250", "--vehicules", "15", "--pietons", "8", "--headless",
    ])
    assert code == 0, "collision, ou point B non atteint"
