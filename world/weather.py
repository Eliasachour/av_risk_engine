"""
Conversion d'un ScenarioContext en paramètres météo CARLA.

Renvoie un dictionnaire dont les clés sont les champs de `carla.WeatherParameters`
(cloudiness, precipitation, fog_density, sun_altitude_angle, …). `carla_world.py`
n'a plus qu'à faire `carla.WeatherParameters(**weather_params(ctx))`.

ATTENTION : la météo CARLA est surtout VISUELLE. L'adhérence réelle des pneus
(le µ qui pilote la dynamique de freinage) se règle séparément via la physique
des roues du véhicule (wheel friction), pas via la météo. Le moteur de risque,
lui, traite déjà µ via `modifiers.mu`. Si tu veux que la dynamique simulée colle
à l'état de route, pense à régler aussi la friction des roues côté CARLA.
"""
from __future__ import annotations

from typing import Dict

from risk_engine.context import EtatRoute, Heure, Meteo, ScenarioContext


def weather_params(ctx: ScenarioContext) -> Dict[str, float]:
    nuit = ctx.heure == Heure.NUIT
    p: Dict[str, float] = dict(
        cloudiness=10.0,
        precipitation=0.0,
        precipitation_deposits=0.0,
        wind_intensity=10.0,
        fog_density=0.0,
        fog_distance=0.0,
        wetness=0.0,
        sun_azimuth_angle=0.0,
        sun_altitude_angle=(-30.0 if nuit else 60.0),
    )

    if ctx.meteo == Meteo.PLUIE:
        p.update(cloudiness=80, precipitation=70, precipitation_deposits=60, wetness=60)
    elif ctx.meteo == Meteo.NEIGE:
        p.update(cloudiness=90, precipitation=80, precipitation_deposits=80, wetness=70)
    elif ctx.meteo == Meteo.BROUILLARD:
        p.update(cloudiness=60, fog_density=80, wetness=10)

    # L'état de route renforce les dépôts au sol (cohérent avec la météo).
    if ctx.etat_route == EtatRoute.MOUILLE:
        p["precipitation_deposits"] = max(p["precipitation_deposits"], 50)
        p["wetness"] = max(p["wetness"], 50)
    elif ctx.etat_route in (EtatRoute.NEIGEUX, EtatRoute.VERGLAS):
        p["precipitation_deposits"] = max(p["precipitation_deposits"], 70)
        p["wetness"] = max(p["wetness"], 60)

    # Distance de brouillard bornée par la visibilité saisie.
    if p["fog_density"] > 0:
        p["fog_distance"] = max(5.0, min(ctx.visibilite_m, 100.0))

    return p
