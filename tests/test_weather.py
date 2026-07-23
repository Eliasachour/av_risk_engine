from risk_engine.context import EtatRoute, Heure, Meteo, ScenarioContext
from world.weather import weather_params


def _ctx(**kw):
    base = dict(vitesse_ego_kmh=50, meteo=Meteo.CLAIR, etat_route=EtatRoute.SEC, heure=Heure.JOUR)
    base.update(kw)
    return ScenarioContext(**base)


def test_clair_jour_sans_pluie():
    p = weather_params(_ctx())
    assert p["precipitation"] == 0
    assert p["sun_altitude_angle"] > 0


def test_pluie_precipitation():
    p = weather_params(_ctx(meteo=Meteo.PLUIE, etat_route=EtatRoute.MOUILLE, visibilite_m=200))
    assert p["precipitation"] > 0
    assert p["wetness"] > 0


def test_nuit_soleil_sous_horizon():
    p = weather_params(_ctx(heure=Heure.NUIT))
    assert p["sun_altitude_angle"] < 0


def test_brouillard_fog():
    p = weather_params(_ctx(meteo=Meteo.BROUILLARD, etat_route=EtatRoute.SEC, visibilite_m=80))
    assert p["fog_density"] > 0
    assert p["fog_distance"] > 0
