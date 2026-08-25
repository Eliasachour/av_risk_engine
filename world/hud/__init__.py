"""HUD Pygame du client CARLA.

API publique :

    from world.hud import HUD, HUDState, MenuConfig, Reglage, ControleMeteo

Modules :

- ``state.py``          : dataclass ``HUDState`` (contrat point d'entrée -> rendu).
- ``palette.py``        : couleurs, dimensions.
- ``pygame_hud.py``     : classe ``HUD`` (rendu principal).
- ``minimap.py``        : mini-carte radar top-down.
- ``menu.py``           : menu de configuration au clavier, dans la même fenêtre.
- ``weather_control.py``: météo pilotable en direct (F1..F7 + réglages fins).
"""
from .menu import MenuConfig, Reglage
from .pygame_hud import HUD
from .state import HUDState
from .weather_control import PRESETS, ControleMeteo

__all__ = ["HUD", "HUDState", "MenuConfig", "Reglage", "ControleMeteo", "PRESETS"]
