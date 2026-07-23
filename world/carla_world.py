"""
Adaptateur CARLA (glu).

Cette partie NÉCESSITE CARLA pour s'exécuter ; sa logique repose sur l'extraction
(testée) et la météo (testée). Elle est volontairement minimaliste : connexion,
mode synchrone, réglage météo, spawn ego + agents, lecture des acteurs, tick.

À adapter selon ta version de CARLA (testé conceptuellement pour 0.9.x) et tes
cartes. Le placement des agents (latéral pour les croisements) est simplifié et
peut être affiné selon les points de spawn de ta carte.
"""
from __future__ import annotations

import math
from typing import List, Optional

import carla  # nécessite le PythonAPI de CARLA (non requis pour les tests d'extraction)

from risk_engine.context import ScenarioContext, TypeAgent
from world.extraction import ActorState, AgentObservation, refresh_context
from world.weather import weather_params

_BP_PAR_TYPE = {
    TypeAgent.VOITURE: "vehicle.tesla.model3",
    TypeAgent.CAMION: "vehicle.carlamotors.firetruck",
    TypeAgent.CYCLISTE: "vehicle.bh.crossbike",
    TypeAgent.PIETON: "walker.pedestrian.0001",
    TypeAgent.OUVRIER: "walker.pedestrian.0001",
}


def _vitesse_ms(actor: "carla.Actor") -> float:
    v = actor.get_velocity()
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def _to_actor_state(actor: "carla.Actor") -> ActorState:
    tr = actor.get_transform()
    return ActorState(
        x=tr.location.x,
        y=tr.location.y,
        yaw_deg=tr.rotation.yaw,
        speed_ms=_vitesse_ms(actor),
    )


class CarlaWorld:
    """Enveloppe minimale autour de l'API CARLA pour exécuter un ScenarioContext."""

    def __init__(self, host: str = "localhost", port: int = 2000, timeout: float = 10.0):
        self.client = carla.Client(host, port)
        self.client.set_timeout(timeout)
        self.world = self.client.get_world()
        self.tm = self.client.get_trafficmanager()
        self._original_settings = self.world.get_settings()
        self.ego: Optional["carla.Actor"] = None
        self.agents: List["carla.Actor"] = []

    # ---------- mode synchrone (reproductibilité) ----------
    def setup_synchronous(self, fixed_delta_seconds: float = 0.05, seed: int = 0) -> None:
        settings = self.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = fixed_delta_seconds
        self.world.apply_settings(settings)
        self.tm.set_synchronous_mode(True)
        self.tm.set_random_device_seed(seed)

    # ---------- application d'un scénario ----------
    def apply_scenario(self, ctx: ScenarioContext) -> None:
        # 1. météo (visuelle)
        self.world.set_weather(carla.WeatherParameters(**weather_params(ctx)))

        bpl = self.world.get_blueprint_library()
        spawn = self.world.get_map().get_spawn_points()[0]

        # 2. ego
        ego_bp = bpl.filter("vehicle.tesla.model3")[0]
        self.ego = self.world.spawn_actor(ego_bp, spawn)

        # 3. agents : placés par rapport à l'ego selon distance + cap relatif
        fwd = spawn.get_forward_vector()
        for ag in ctx.agents:
            loc = carla.Location(
                x=spawn.location.x + fwd.x * ag.distance_m,
                y=spawn.location.y + fwd.y * ag.distance_m,
                z=spawn.location.z + 0.3,
            )
            rot = carla.Rotation(yaw=spawn.rotation.yaw + ag.cap_relatif_deg)
            bp_name = _BP_PAR_TYPE.get(ag.type_agent, "vehicle.tesla.model3")
            bp = bpl.filter(bp_name)[0]
            actor = self.world.try_spawn_actor(bp, carla.Transform(loc, rot))
            if actor is not None:
                self.agents.append(actor)

        self.world.tick()

    # ---------- lecture de l'état du monde ----------
    def read_context(self, base: ScenarioContext) -> ScenarioContext:
        """Reconstruit un ScenarioContext à jour depuis les acteurs CARLA."""
        ego_state = _to_actor_state(self.ego)
        observations = [
            AgentObservation(
                state=_to_actor_state(actor),
                type_agent=base.agents[i].type_agent if i < len(base.agents) else TypeAgent.VOITURE,
                profondeur_mesuree=base.agents[i].profondeur_mesuree if i < len(base.agents) else True,
            )
            for i, actor in enumerate(self.agents)
        ]
        return refresh_context(base, ego_state, observations)

    def step(self) -> None:
        self.world.tick()

    # ---------- nettoyage ----------
    def cleanup(self) -> None:
        for a in self.agents:
            if a.is_alive:
                a.destroy()
        if self.ego is not None and self.ego.is_alive:
            self.ego.destroy()
        self.world.apply_settings(self._original_settings)
        self.tm.set_synchronous_mode(False)
