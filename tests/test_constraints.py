from risk_engine.context import (
    EtatRoute, Heure, Meteo, ScenarioContext, TypeRoute,
)
from scenarios import constraints


def _ctx(**kw):
    base = dict(
        vitesse_ego_kmh=90, type_route=TypeRoute.NATIONALE,
        limite_vitesse_kmh=90, meteo=Meteo.CLAIR, etat_route=EtatRoute.SEC,
        heure=Heure.JOUR, visibilite_m=400,
    )
    base.update(kw)
    return ScenarioContext(**base)


def test_pluie_incompatible_avec_sec():
    pbs = constraints.valider(_ctx(meteo=Meteo.PLUIE, etat_route=EtatRoute.SEC, visibilite_m=200))
    assert any("sec" in p.lower() or "incompatible" in p.lower() for p in pbs)


def test_pluie_mouille_coherent():
    pbs = constraints.valider(_ctx(meteo=Meteo.PLUIE, etat_route=EtatRoute.MOUILLE, visibilite_m=200))
    assert pbs == []


def test_etats_compatibles_clair():
    assert constraints.etats_route_compatibles(Meteo.CLAIR) == [EtatRoute.SEC]


def test_nuit_reduit_visibilite():
    _, vmax_jour = constraints.plage_visibilite(Meteo.CLAIR, Heure.JOUR)
    _, vmax_nuit = constraints.plage_visibilite(Meteo.CLAIR, Heure.NUIT)
    assert vmax_nuit < vmax_jour


def test_limites_autoroute():
    assert constraints.limites_compatibles(TypeRoute.AUTOROUTE) == [110, 130]


def test_zone_travaux_ajoute_limites_basses():
    lim = constraints.limites_compatibles(TypeRoute.AUTOROUTE, zone_travaux=True)
    assert 70 in lim and 110 in lim


def test_limite_non_plausible():
    pbs = constraints.valider(_ctx(type_route=TypeRoute.URBAIN, limite_vitesse_kmh=130,
                                   vitesse_ego_kmh=50))
    assert any("plausible" in p.lower() for p in pbs)


def test_vitesse_ego_excessive():
    pbs = constraints.valider(_ctx(limite_vitesse_kmh=80, vitesse_ego_kmh=130))
    assert any("ego" in p.lower() for p in pbs)


def test_scenario_coherent():
    assert constraints.est_coherent(_ctx())
