"""Adaptateur monde : extraction géométrique (pure) et glu CARLA.

Note : `carla_world` n'est pas importé ici car il dépend du module `carla`.
Importez-le explicitement (`from world.carla_world import CarlaWorld`) seulement
quand CARLA est disponible. L'extraction et la météo, elles, sont pures.
"""
from world.extraction import (
    ActorState,
    AgentObservation,
    agent_from_observation,
    planar_distance,
    refresh_context,
    relative_heading_deg,
)
from world.weather import weather_params

__all__ = [
    "ActorState",
    "AgentObservation",
    "planar_distance",
    "relative_heading_deg",
    "agent_from_observation",
    "refresh_context",
    "weather_params",
]
