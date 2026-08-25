"""Mini-simulateur cinématique 2D (substitut de CARLA) et visualisation."""
from sim.kinematic import Frame, collision, diagnostic_collision, run

__all__ = ["Frame", "run", "collision", "diagnostic_collision"]
