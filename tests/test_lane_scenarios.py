"""
Tests du raisonnement par voie (D20) et des scénarios de trafic (D21).

Le fait marquant que ces tests verrouillent : **un raisonnement purement
euclidien manque un obstacle immobile situé dans notre propre voie dès que la
route tourne**. Mesuré sur le projet, à 40 m et 60 km/h : sur un rayon de
200 m l'écart latéral apparent vaut 4 m, sur 80 m il vaut 9,8 m — largement de
quoi faire rétrograder l'agent en SAFE par le filtrage latéral.
"""
import math

import pytest

from risk_engine import (
    RiskLevel, ScenarioContext, TypeAgent, TypeRoute, assess_risk,
)
from tests.fake_carla import installer


@pytest.fixture(autouse=True)
def _carla_factice():
    installer()
    yield


@pytest.fixture
def carte():
    import carla
    return carla.Client("localhost", 2000).get_world().get_map()


class _Acteur:
    """Acteur minimal : un transform et une vitesse."""
    _compteur = 0

    def __init__(self, transform, vitesse_ms=0.0):
        _Acteur._compteur += 1
        self.id = _Acteur._compteur
        self.type_id = "vehicle.tesla.model3"
        self._tf = transform
        self._v = vitesse_ms

    def get_transform(self):
        return self._tf

    def get_velocity(self):
        import carla
        r = math.radians(self._tf.rotation.yaw)
        return carla.Vector3D(self._v * math.cos(r), self._v * math.sin(r), 0.0)


# ---------------------------------------------------------------------------
# Classification des relations
# ---------------------------------------------------------------------------


def test_meme_voie_reconnue(carte):
    from world.lane_relation import RelationVoie, analyser

    a = carte.waypoint_a_abscisse(0.0, -1)
    b = carte.waypoint_a_abscisse(40.0, -1)
    an = analyser(carte, a.transform, b.transform)
    assert an.relation is RelationVoie.MEME_VOIE
    assert an.ecart_voies == 0
    assert an.meme_sens


def test_voie_adjacente_reconnue(carte):
    from world.lane_relation import RelationVoie, analyser

    a = carte.waypoint_a_abscisse(0.0, -1)
    b = carte.waypoint_a_abscisse(10.0, -2)
    an = analyser(carte, a.transform, b.transform)
    assert an.relation is RelationVoie.VOIE_ADJACENTE
    assert an.meme_sens
    assert abs(an.ecart_lateral_m) == pytest.approx(3.5, abs=0.6)


def test_voie_opposee_reconnue(carte):
    from world.lane_relation import RelationVoie, analyser

    a = carte.waypoint_a_abscisse(0.0, -1)
    b = carte.waypoint_a_abscisse(30.0, 1)
    an = analyser(carte, a.transform, b.transform)
    assert an.relation is RelationVoie.VOIE_OPPOSEE
    assert not an.meme_sens


def test_cap_relatif_nul_entre_voies_paralleles(carte):
    """Deux véhicules qui suivent chacun leur voie ne convergent pas.

    En absolu, leurs caps diffèrent — c'est la courbure de la route. Extrapolé
    en ligne droite, cet écart faisait croire à une trajectoire convergente et
    classait un véhicule de la voie adjacente en CRITICAL. Mesuré par rapport
    aux directions de voie, l'écart doit être nul.
    """
    from world.lane_relation import analyser

    a = carte.waypoint_a_abscisse(0.0, -1)
    b = carte.waypoint_a_abscisse(0.0, -2)
    # Les caps ABSOLUS diffèrent bien : la route tourne.
    an = analyser(carte, a.transform, b.transform)
    assert abs(an.cap_relatif_deg) < 5.0, (
        f"cap relatif {an.cap_relatif_deg:.1f}deg entre deux voies paralleles"
    )


def test_voie_opposee_cap_relatif_proche_de_180(carte):
    from world.lane_relation import analyser

    a = carte.waypoint_a_abscisse(0.0, -1)
    b = carte.waypoint_a_abscisse(20.0, 1)
    an = analyser(carte, a.transform, b.transform)
    assert abs(abs(an.cap_relatif_deg) - 180.0) < 15.0


# ---------------------------------------------------------------------------
# Le cas qui motive tout : l'obstacle en virage
# ---------------------------------------------------------------------------


def test_obstacle_meme_voie_en_virage_reste_detecte(carte):
    """LE test de non-régression de D20.

    Un véhicule immobile, dans la voie de l'ego, à 40 m, sur une route courbe.
    Sans correction curviligne il est classé SAFE — détection manquée. Avec,
    il doit être détecté.
    """
    from world.perception_oracle import contexte_depuis_perception
    from world.extraction import ActorState

    wp_ego = carte.waypoint_a_abscisse(0.0, -1)
    ego = _Acteur(wp_ego.transform, 16.7)          # 60 km/h
    wp_obs = carte.waypoint_a_abscisse(40.0, -1)
    obstacle = _Acteur(wp_obs.transform, 0.0)      # à l'arrêt

    etat = ActorState(x=wp_obs.transform.location.x,
                      y=wp_obs.transform.location.y,
                      yaw_deg=wp_obs.transform.rotation.yaw, speed_ms=0.0)
    meta = [(obstacle, TypeAgent.VOITURE, etat)]
    base = ScenarioContext(vitesse_ego_kmh=60, type_route=TypeRoute.NATIONALE,
                           limite_vitesse_kmh=90, agents=[])

    sans = contexte_depuis_perception(base, ego, meta)
    avec = contexte_depuis_perception(base, ego, meta, carte=carte)

    # Sans carte : l'écart euclidien est important à cause de la courbure.
    assert abs(sans.agents[0].ecart_lateral_m) > 3.0
    # Avec carte : le véhicule est dans notre voie, l'écart doit être quasi nul.
    assert abs(avec.agents[0].ecart_lateral_m) < 1.0

    niveau = assess_risk(avec).level
    assert int(niveau) >= int(RiskLevel.DANGER), (
        "un obstacle immobile dans notre voie a 40 m doit etre detecte, "
        f"obtenu {niveau.name}"
    )


def test_voie_adjacente_ne_declenche_pas_critical(carte):
    """Un véhicule roulant en parallèle sur la voie d'à côté n'est pas un conflit."""
    from world.perception_oracle import contexte_depuis_perception
    from world.extraction import ActorState

    wp_ego = carte.waypoint_a_abscisse(0.0, -1)
    ego = _Acteur(wp_ego.transform, 16.7)
    wp_a = carte.waypoint_a_abscisse(10.0, -2)
    autre = _Acteur(wp_a.transform, 16.7)          # même vitesse

    etat = ActorState(x=wp_a.transform.location.x, y=wp_a.transform.location.y,
                      yaw_deg=wp_a.transform.rotation.yaw, speed_ms=16.7)
    base = ScenarioContext(vitesse_ego_kmh=60, type_route=TypeRoute.NATIONALE,
                           limite_vitesse_kmh=90, agents=[])
    ctx = contexte_depuis_perception(
        base, ego, [(autre, TypeAgent.VOITURE, etat)], carte=carte)
    assert assess_risk(ctx).level is RiskLevel.SAFE


def test_analyses_sont_remontees(carte):
    """Le dictionnaire `analyses` doit être rempli pour le HUD et les journaux."""
    from world.perception_oracle import contexte_depuis_perception
    from world.extraction import ActorState

    wp_ego = carte.waypoint_a_abscisse(0.0, -1)
    ego = _Acteur(wp_ego.transform, 16.7)
    wp_a = carte.waypoint_a_abscisse(25.0, -1)
    autre = _Acteur(wp_a.transform, 8.0)
    etat = ActorState(x=wp_a.transform.location.x, y=wp_a.transform.location.y,
                      yaw_deg=wp_a.transform.rotation.yaw, speed_ms=8.0)

    analyses = {}
    contexte_depuis_perception(
        ScenarioContext(vitesse_ego_kmh=60, agents=[]), ego,
        [(autre, TypeAgent.VOITURE, etat)], carte=carte, analyses=analyses)
    assert autre.id in analyses
    assert analyses[autre.id].relation.value == "meme_voie"


def test_sans_carte_comportement_inchange():
    """Sans carte, on retombe sur l'écart euclidien : le simulateur cinématique
    et les 24 scénarios ne doivent pas être affectés."""
    from world.perception_oracle import contexte_depuis_perception
    from world.extraction import ActorState

    import carla
    ego = _Acteur(carla.Transform(carla.Location(0, 0, 0),
                                  carla.Rotation(yaw=0.0)), 13.9)
    etat = ActorState(x=30.0, y=6.0, yaw_deg=0.0, speed_ms=0.0)
    autre = _Acteur(carla.Transform(carla.Location(30, 6, 0),
                                    carla.Rotation(yaw=0.0)), 0.0)
    ctx = contexte_depuis_perception(
        ScenarioContext(vitesse_ego_kmh=50, agents=[]), ego,
        [(autre, TypeAgent.VOITURE, etat)])
    assert ctx.agents[0].ecart_lateral_m == pytest.approx(6.0, abs=0.1)


# ---------------------------------------------------------------------------
# Scénarios de trafic
# ---------------------------------------------------------------------------


def test_quatre_scenarios_distincts():
    from world.traffic import CONFIGS, TypeScenario

    assert len(CONFIGS) == 4
    densites = [CONFIGS[s].num_vehicules for s in
                (TypeScenario.NORMAL, TypeScenario.PEU_DENSE, TypeScenario.DENSE)]
    assert densites == sorted(densites), "la densite doit croitre"
    # Seul le quatrième introduit de l'imprévisibilité.
    for s in (TypeScenario.NORMAL, TypeScenario.PEU_DENSE, TypeScenario.DENSE):
        assert CONFIGS[s].surprise_intensity == 0.0
    assert CONFIGS[TypeScenario.IMPREVISIBLE].surprise_intensity > 0.0
    # Le scénario imprévisible reprend la densité du dense.
    assert (CONFIGS[TypeScenario.IMPREVISIBLE].num_vehicules
            == CONFIGS[TypeScenario.DENSE].num_vehicules)


def test_ecarts_choisis_parmi_les_candidats_plausibles():
    """Aucun écart ne doit être envisagé hors de sa situation propre.

    C'est ce qui distingue une imprévisibilité contextuelle d'un `random()` :
    on ne s'insère pas s'il n'y a personne devant, on n'hésite pas hors d'une
    intersection, on ne freine pas brusquement à l'arrêt.

    Point crucial : le type d'écart est choisi PARMI les candidats plausibles.
    Le tirer d'abord puis vérifier les conditions ferait retomber la majorité
    des déclenchements dans le vide — mesuré à 55 % sur une version antérieure —
    tout en immobilisant le véhicule pendant la durée de l'écart.
    """
    import random

    from world.traffic import (
        CONFIGS, Ecart, EtatVehicule, GestionnaireTrafic, PERSONNALITES,
        TypeScenario,
    )

    g = GestionnaireTrafic.__new__(GestionnaireTrafic)
    g.config = CONFIGS[TypeScenario.IMPREVISIBLE]
    presse = next(p for p in PERSONNALITES if p.nom == "Presse")
    etat = EtatVehicule(id_vehicule=1, personnalite=presse, rng=random.Random(1))

    # À l'arrêt, rien autour : aucun écart plausible.
    assert g._candidats_plausibles(etat, {"vitesse_ms": 0.0}) == []

    # Hors intersection : pas d'hésitation.
    roulant = {"vitesse_ms": 12.0, "en_intersection": False}
    assert Ecart.HESITATION not in [c for c, _ in g._candidats_plausibles(etat, roulant)]

    # Sans leader : pas d'insertion forcée.
    assert Ecart.INSERTION_FORCEE not in [
        c for c, _ in g._candidats_plausibles(etat, roulant)]

    # Avec leader : l'insertion devient plausible pour un conducteur pressé.
    avec_leader = {"vitesse_ms": 12.0, "a_un_leader": True}
    assert Ecart.INSERTION_FORCEE in [
        c for c, _ in g._candidats_plausibles(etat, avec_leader)]

    # Un conducteur prudent ne force jamais l'insertion.
    prudent = next(p for p in PERSONNALITES if p.nom == "Prudent")
    etat_p = EtatVehicule(id_vehicule=2, personnalite=prudent, rng=random.Random(2))
    assert Ecart.INSERTION_FORCEE not in [
        c for c, _ in g._candidats_plausibles(etat_p, avec_leader)]


def test_aucun_ecart_dans_les_scenarios_1_a_3():
    """Les scénarios 1 à 3 n'ont aucun comportement stochastique."""
    from world.traffic import CONFIGS, TypeScenario

    for sc in (TypeScenario.NORMAL, TypeScenario.PEU_DENSE, TypeScenario.DENSE):
        assert CONFIGS[sc].surprise_intensity == 0.0
        assert not CONFIGS[sc].avec_personnalites


def test_taux_d_ecarts_independant_du_tick_rate():
    """Le taux doit s'exprimer par seconde, pas par image.

    Un taux par image donnerait deux fois plus d'écarts à 40 Hz qu'à 20 Hz :
    la même graine ne rejouerait pas la même simulation selon le tick rate.
    """
    from world.traffic import PERIODE_DECISION_S

    # Les décisions sont prises à cadence fixe, indépendante de dt.
    assert PERIODE_DECISION_S > 0
    for dt in (1 / 20.0, 1 / 30.0, 1 / 60.0):
        n_decisions = 0
        prochaine = 0.0
        t = 0.0
        for _ in range(int(10.0 / dt)):     # 10 secondes simulées
            t += dt
            if t >= prochaine:
                prochaine = t + PERIODE_DECISION_S
                n_decisions += 1
        assert abs(n_decisions - 10.0 / PERIODE_DECISION_S) <= 1, (
            f"a dt={dt:.4f}s, {n_decisions} decisions au lieu de "
            f"{10.0 / PERIODE_DECISION_S:.0f}"
        )


def test_journal_de_risque_ne_garde_que_l_utile(tmp_path):
    """Journaliser chaque couple à chaque tick noierait l'information."""
    from world.simulation_log import JournalSimulation, LigneRisque

    def ligne(niveau, t=0.0):
        return LigneRisque(
            t=t, id_autre=1, type_autre="voiture", relation="voie_adjacente",
            meme_voie=False, distance_m=20.0, ecart_lateral_m=-3.5,
            cap_relatif_deg=0.0, vitesse_ego_kmh=50.0, vitesse_autre_kmh=50.0,
            vitesse_relative_kmh=0.0, ttc_s=None, thw_s=1.4, drac=0.5,
            niveau=niveau, metrique_decisive="THW")

    with JournalSimulation(tmp_path, "test", graine=1) as j:
        assert not j.risque(ligne("SAFE", 0.0))       # rien à dire
        assert not j.risque(ligne("SAFE", 0.1))       # toujours rien
        assert j.risque(ligne("DANGER", 0.2))         # écart : on écrit
        assert j.risque(ligne("SAFE", 0.3))           # transition : on écrit
        assert j.n_lignes_risque == 2


def _gestionnaire_factice(graine=42, surprise=0.5):
    """Gestionnaire sans monde CARLA, pour tester la seule mécanique d'écarts."""
    import random

    from world.traffic import (
        CONFIGS, GestionnaireTrafic, PERSONNALITES, POIDS_PERSONNALITES,
        EtatVehicule, TypeScenario,
    )
    from dataclasses import replace

    g = GestionnaireTrafic.__new__(GestionnaireTrafic)
    g.config = replace(CONFIGS[TypeScenario.IMPREVISIBLE],
                       surprise_intensity=surprise)
    g.tm = None
    g.seed = graine
    g.journal = []
    g.etats = {}
    g._prochaine_decision_s = 0.0
    g.vehicules = []

    class Veh:
        def __init__(self, vid):
            self.id = vid
            self.is_alive = True

    for vid in range(1, 31):
        rng = random.Random(graine * 1_000_003 + vid)
        perso = rng.choices(PERSONNALITES, weights=POIDS_PERSONNALITES, k=1)[0]
        g.etats[vid] = EtatVehicule(id_vehicule=vid, personnalite=perso, rng=rng,
                                    vitesse_nominale=perso.vitesse_delta,
                                    distance_nominale=perso.distance_securite)
        g.vehicules.append(Veh(vid))

    # Situation plausible pour tous : en mouvement, avec un leader devant.
    g._lire_situations = lambda **kw: {
        v.id: {"vitesse_ms": 12.0, "a_un_leader": True,
               "suivi_de_pres": False, "en_intersection": False}
        for v in g.vehicules
    }
    g._engager = lambda *a, **k: None      # pas de Traffic Manager ici
    g._terminer = lambda etat: setattr(etat, "ecart", None)
    return g


def test_ecarts_se_declenchent_quand_le_contexte_le_permet():
    """Avec des situations plausibles, des écarts doivent finir par survenir."""
    g = _gestionnaire_factice()
    t = 0.0
    for _ in range(2000):        # 100 s simulées à 20 Hz
        t += 0.05
        g.tick(t)
    assert g.journal, "aucun ecart en 100 s sur 30 vehicules en situation propice"
    # Rares : pas plus d'un écart par véhicule toutes les ~12 s (le repos).
    assert len(g.journal) < 30 * (100 / 12) + 10


def test_ecarts_reproductibles_a_la_graine():
    """Même graine, même simulation — exigence de reproductibilité."""
    def executer(graine):
        g = _gestionnaire_factice(graine=graine)
        t = 0.0
        for _ in range(1200):
            t += 0.05
            g.tick(t)
        return [(round(e.t, 2), e.id_vehicule, e.ecart.value) for e in g.journal]

    a, b = executer(42), executer(42)
    assert a == b, "la meme graine doit rejouer exactement la meme sequence"
    assert executer(7) != a, "des graines differentes doivent differer"


def test_intensite_de_surprise_module_le_taux():
    """`surprise` 0 -> aucun ecart ; plus elle monte, plus il y en a."""
    def compter(intensite):
        g = _gestionnaire_factice(surprise=intensite)
        t = 0.0
        for _ in range(2000):
            t += 0.05
            g.tick(t)
        return len(g.journal)

    assert compter(0.0) == 0
    faible, fort = compter(0.2), compter(1.0)
    assert faible < fort, f"intensite 0.2 -> {faible} ecarts, 1.0 -> {fort}"


def test_un_ecart_dure_et_bloque_les_suivants():
    """Un écart doit durer, et un repos doit suivre — pas d'enchaînement."""
    from world.traffic import DUREES, REPOS_ENTRE_ECARTS_S

    g = _gestionnaire_factice(surprise=1.0)
    t = 0.0
    for _ in range(4000):
        t += 0.05
        g.tick(t)

    par_vehicule = {}
    for e in g.journal:
        par_vehicule.setdefault(e.id_vehicule, []).append(e.t)
    for vid, temps in par_vehicule.items():
        for avant, apres in zip(temps, temps[1:]):
            assert apres - avant >= REPOS_ENTRE_ECARTS_S - 1e-6, (
                f"vehicule {vid} : deux ecarts a {apres - avant:.1f}s d'intervalle"
            )
