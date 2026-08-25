"""Adaptateur monde : géométrie pure, météo, et glu CARLA.

Ce paquet réunit tout ce qui touche à l'environnement d'exécution du moteur :

- **Modules purs** (importés d'office ici) — utilisables sans CARLA :
  - ``extraction`` : géométrie pure, partagée par le simulateur et CARLA.
  - ``weather`` : conversion contexte → ``carla.WeatherParameters``.

- **Modules CARLA** (à importer explicitement) — nécessitent le paquet ``carla`` :
  - ``carla_bridge`` : pont de perception (connexion, spawn, tick).
  - ``carla_control`` : pilotage latéral + reprise ACC.
  - ``carla_form`` : formulaire tkinter de configuration.
  - ``hud`` : sous-package du HUD Pygame.
  - ``carla_world`` : glu CARLA historique (superseded par ``carla_bridge``).
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
