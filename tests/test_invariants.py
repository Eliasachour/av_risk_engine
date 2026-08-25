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


def test_rss_croit_quand_l_adherence_baisse():
    """La distance RSS doit AUGMENTER quand la chaussée se dégrade.

    Le modèle RSS suppose une décélération garantie `b_min` pour l'ego. Cette
    décélération ne peut pas dépasser l'adhérence disponible µ·g : sur verglas
    (µ·g ≈ 2,9 m/s²), promettre 4 m/s² sous-estimerait la distance de sécurité
    exactement là où il faut être le plus prudent. Le moteur plafonne donc
    b_min à µ·g (voir DECISIONS.md, D14).
    """
    def _rss(etat, meteo):
        ctx = ScenarioContext(vitesse_ego_kmh=90, etat_route=etat, meteo=meteo,
                              agents=[Agent(TypeAgent.VOITURE, 80, 70, 0)])
        return assess_risk(ctx).details[0].rss_min

    sec = _rss(EtatRoute.SEC, Meteo.CLAIR)
    verglas = _rss(EtatRoute.VERGLAS, Meteo.NEIGE)
    assert verglas > sec, (
        f"RSS sur verglas ({verglas:.1f} m) doit dépasser celui sur sec "
        f"({sec:.1f} m) : l'ego ne peut pas freiner aussi fort."
    )


def test_rss_jamais_inferieur_a_la_distance_d_arret_sur_sol_degrade():
    """Sur sol très dégradé, le RSS doit rester du même ordre que la distance
    d'arrêt physique — sinon la métrique promet une sécurité qui n'existe pas."""
    import math as _math
    from risk_engine import metrics as _metrics, modifiers as _modifiers

    ctx = ScenarioContext(vitesse_ego_kmh=90, etat_route=EtatRoute.VERGLAS,
                          meteo=Meteo.NEIGE,
                          agents=[Agent(TypeAgent.VOITURE, 0, 120, 0)])
    rss = assess_risk(ctx).details[0].rss_min
    mu_g = _modifiers.mu(EtatRoute.VERGLAS) * _metrics.G
    d_arret = (90 / 3.6) ** 2 / (2 * mu_g)
    # Le RSS face à un obstacle fixe doit couvrir au moins la distance d'arrêt.
    assert rss >= d_arret * 0.9, (
        f"RSS={rss:.0f} m insuffisant face à une distance d'arrêt de {d_arret:.0f} m"
    )
