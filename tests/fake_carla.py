"""
Faux module CARLA — permet de tester la chaîne d'intégration sans GPU.

**Ce n'est pas un simulateur.** C'est un double de test (*test double*) qui
implémente juste assez de l'API CARLA pour que le code d'intégration s'exécute
de bout en bout : connexion, chargement de carte, spawn, tick, capteurs,
contrôle. La physique est réduite à une intégration cinématique élémentaire.

Raison d'être : le code CARLA a été écrit sans accès à un serveur, et quatre
erreurs d'API sont passées en production (`get_synchronous_mode` inexistant,
`to_carla_weather` mal nommé, `contexte_courant` appelé sans argument, tick
manquant avant le spawn du trafic). Chacune aurait été détectée ici en une
seconde. Ce double sert donc de **filet de sécurité sur les signatures et
l'enchaînement des appels**, pas sur le comportement physique.

Usage :

    import sys
    from tests.fake_carla import installer
    installer()          # place le faux module dans sys.modules["carla"]
    # ... importer et exécuter le code d'intégration ...

Limites assumées : pas de collision réelle, pas de navmesh, pas de rendu. Les
capteurs émettent des événements déclenchés par des règles simples.
"""
from __future__ import annotations

import math
import sys
import types
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Types géométriques
# ---------------------------------------------------------------------------


class Location:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def distance(self, autre: "Location") -> float:
        return math.sqrt((self.x - autre.x) ** 2 + (self.y - autre.y) ** 2
                         + (self.z - autre.z) ** 2)

    def __repr__(self):
        return f"Location({self.x:.1f}, {self.y:.1f}, {self.z:.1f})"


class Rotation:
    def __init__(self, pitch: float = 0.0, yaw: float = 0.0, roll: float = 0.0):
        self.pitch, self.yaw, self.roll = float(pitch), float(yaw), float(roll)


class Vector3D:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)


class Transform:
    def __init__(self, location: Optional[Location] = None,
                 rotation: Optional[Rotation] = None):
        self.location = location or Location()
        self.rotation = rotation or Rotation()

    def get_forward_vector(self) -> Vector3D:
        r = math.radians(self.rotation.yaw)
        return Vector3D(math.cos(r), math.sin(r), 0.0)


class VehicleControl:
    def __init__(self, throttle: float = 0.0, steer: float = 0.0,
                 brake: float = 0.0, hand_brake: bool = False,
                 reverse: bool = False, manual_gear_shift: bool = False,
                 gear: int = 0):
        self.throttle, self.steer, self.brake = throttle, steer, brake
        self.hand_brake, self.reverse = hand_brake, reverse


class WeatherParameters:
    def __init__(self, **kwargs):
        # Accepte tous les champs météo CARLA sans en exiger aucun.
        for k, v in kwargs.items():
            setattr(self, k, v)


class TrafficLightState:
    Red = "Red"
    Yellow = "Yellow"
    Green = "Green"
    Off = "Off"
    Unknown = "Unknown"


class LaneType:
    Driving = "Driving"
    Sidewalk = "Sidewalk"
    Any = "Any"


# ---------------------------------------------------------------------------
# Physique des roues (pour appliquer_friction)
# ---------------------------------------------------------------------------


class WheelPhysicsControl:
    def __init__(self, tire_friction: float = 3.5):
        self.tire_friction = tire_friction


class VehiclePhysicsControl:
    def __init__(self):
        self.wheels = [WheelPhysicsControl() for _ in range(4)]


# ---------------------------------------------------------------------------
# Blueprints
# ---------------------------------------------------------------------------


class ActorBlueprint:
    def __init__(self, bp_id: str):
        self.id = bp_id
        self._attributs: Dict[str, str] = {"role_name": "autopilot"}
        if bp_id.startswith("vehicle."):
            self._attributs["color"] = "255,0,0"
        if bp_id.startswith("walker."):
            self._attributs["is_invincible"] = "true"
        if bp_id.startswith("sensor.camera"):
            self._attributs.update(image_size_x="800", image_size_y="600", fov="90")
        if bp_id.startswith("sensor.other.obstacle"):
            self._attributs.update(distance="5", hit_radius="0.5",
                                   only_dynamics="false", sensor_tick="0.0")

    def has_attribute(self, nom: str) -> bool:
        return nom in self._attributs

    def get_attribute(self, nom: str):
        valeur = self._attributs.get(nom, "")
        return types.SimpleNamespace(
            recommended_values=[valeur] if valeur else [],
            __str__=lambda self=None: valeur,
        )

    def set_attribute(self, nom: str, valeur: str) -> None:
        self._attributs[nom] = str(valeur)


#: Catalogue minimal, calqué sur les identifiants réels de CARLA 0.9.x.
_CATALOGUE = [
    "vehicle.tesla.model3", "vehicle.audi.a2", "vehicle.audi.tt",
    "vehicle.bmw.grandtourer", "vehicle.carlamotors.firetruck",
    "vehicle.mercedes.sprinter", "vehicle.bh.crossbike",
    "vehicle.diamondback.century",
    "walker.pedestrian.0001", "walker.pedestrian.0002",
    "walker.pedestrian.0003", "walker.pedestrian.0004",
    "sensor.camera.rgb", "sensor.other.obstacle", "sensor.other.collision",
    "controller.ai.walker",
]


class BlueprintLibrary:
    def __init__(self, catalogue: Optional[List[str]] = None):
        self._ids = list(catalogue if catalogue is not None else _CATALOGUE)

    def filter(self, motif: str) -> List[ActorBlueprint]:
        if motif.endswith("*"):
            prefixe = motif[:-1]
            return [ActorBlueprint(i) for i in self._ids if i.startswith(prefixe)]
        return [ActorBlueprint(i) for i in self._ids if i == motif]

    def find(self, bp_id: str) -> ActorBlueprint:
        if bp_id not in self._ids:
            raise IndexError(f"blueprint introuvable : {bp_id}")
        return ActorBlueprint(bp_id)


# ---------------------------------------------------------------------------
# Acteurs
# ---------------------------------------------------------------------------


class Actor:
    _prochain_id = 1

    def __init__(self, blueprint: ActorBlueprint, transform: Transform, world):
        self.id = Actor._prochain_id
        Actor._prochain_id += 1
        self.type_id = blueprint.id
        self.attributes = dict(blueprint._attributs)
        self._tf = transform
        self._vitesse = Vector3D()
        self.is_alive = True
        self._world = world
        self._controle = VehicleControl()
        self._physique = VehiclePhysicsControl()
        self._autopilot = False
        self._feu = TrafficLightState.Green
        self._limite = 50.0

    # -- pose et vitesse ---------------------------------------------------
    def get_transform(self) -> Transform:
        return self._tf

    def set_transform(self, tf: Transform) -> None:
        self._tf = tf

    def get_location(self) -> Location:
        return self._tf.location

    def get_velocity(self) -> Vector3D:
        return self._vitesse

    def set_target_velocity(self, v: Vector3D) -> None:
        self._vitesse = v

    # -- contrôle ---------------------------------------------------------
    def apply_control(self, controle: VehicleControl) -> None:
        self._controle = controle

    def get_control(self) -> VehicleControl:
        return self._controle

    def set_autopilot(self, actif: bool, port: int = 8000) -> None:
        self._autopilot = actif

    def get_physics_control(self) -> VehiclePhysicsControl:
        return self._physique

    def apply_physics_control(self, physique: VehiclePhysicsControl) -> None:
        self._physique = physique

    # -- environnement ----------------------------------------------------
    def get_speed_limit(self) -> float:
        return self._limite

    def is_at_traffic_light(self) -> bool:
        return False

    def get_traffic_light_state(self):
        return self._feu

    # -- capteurs ---------------------------------------------------------
    def listen(self, callback: Callable) -> None:
        self._world._abonnes.setdefault(self.id, []).append((self, callback))

    def stop(self) -> None:
        self._world._abonnes.pop(self.id, None)

    # -- contrôleur de piéton --------------------------------------------
    def start(self) -> None:
        pass

    def go_to_location(self, loc: Location) -> None:
        pass

    def set_max_speed(self, v: float) -> None:
        pass

    def destroy(self) -> bool:
        self.is_alive = False
        self._world._acteurs = [a for a in self._world._acteurs if a.id != self.id]
        self._world._abonnes.pop(self.id, None)
        return True

    def __repr__(self):
        return f"<Actor {self.id} {self.type_id}>"


# ---------------------------------------------------------------------------
# Carte
# ---------------------------------------------------------------------------


class Waypoint:
    """Waypoint avec identifiants de voie, comme le vrai CARLA.

    Sans `road_id` / `lane_id`, impossible de tester le raisonnement par voie —
    et c'est justement lui qui corrige la detection manquee en virage.
    """

    def __init__(self, transform: Transform, lane_width: float = 3.5,
                 road_id: int = 0, lane_id: int = -1, section_id: int = 0,
                 s: float = 0.0, is_junction: bool = False, carte=None):
        self.transform = transform
        self.lane_width = lane_width
        self.road_id = road_id
        self.lane_id = lane_id
        self.section_id = section_id
        self.s = s
        self.is_junction = is_junction
        self.lane_type = LaneType.Driving
        self._carte = carte

    def next(self, distance: float) -> List["Waypoint"]:
        if self._carte is not None:
            return [self._carte.waypoint_a_abscisse(self.s + distance, self.lane_id)]
        r = math.radians(self.transform.rotation.yaw)
        loc = Location(self.transform.location.x + distance * math.cos(r),
                       self.transform.location.y + distance * math.sin(r),
                       self.transform.location.z)
        return [Waypoint(Transform(loc, Rotation(yaw=self.transform.rotation.yaw)),
                         self.lane_width, self.road_id, self.lane_id,
                         self.section_id, self.s + distance)]

    def get_left_lane(self) -> Optional["Waypoint"]:
        if self._carte is None:
            return None
        return self._carte.waypoint_a_abscisse(self.s, self.lane_id - 1)

    def get_right_lane(self) -> Optional["Waypoint"]:
        if self._carte is None:
            return None
        return self._carte.waypoint_a_abscisse(self.s, self.lane_id + 1)


class Map:
    def __init__(self, nom: str, n_spawn: int = 60):
        self.name = nom
        # Points de spawn répartis sur un anneau LOIN de l'origine — c'est
        # ainsi que sont les vraies cartes, et c'est ce qui a révélé le bug du
        # filtrage par distance sur un ego encore situé en (0, 0, 0).
        self._spawn = []
        for i in range(n_spawn):
            lane_id = self.VOIES[i % len(self.VOIES)]
            rayon = self._rayon_de_voie(lane_id)
            theta = 2 * math.pi * i / n_spawn
            sens = -1.0 if lane_id < 0 else 1.0
            self._spawn.append(Transform(
                Location(self.CENTRE[0] + rayon * math.cos(theta),
                         self.CENTRE[1] + rayon * math.sin(theta), 0.3),
                Rotation(yaw=math.degrees(theta + sens * math.pi / 2.0)),
            ))

    def get_spawn_points(self) -> List[Transform]:
        return list(self._spawn)

    # --- Reseau routier : une rocade circulaire a 4 voies ------------------
    # Deux voies dans chaque sens. La COURBURE est essentielle : c'est elle qui
    # met en defaut un raisonnement purement euclidien et justifie le passage
    # aux coordonnees de voie.
    CENTRE = (200.0, 180.0)
    RAYON_AXE = 120.0
    LARGEUR_VOIE = 3.5
    #: lane_id negatifs = sens horaire, positifs = sens antihoraire.
    VOIES = (-2, -1, 1, 2)

    def _rayon_de_voie(self, lane_id: int) -> float:
        """Rayon de l'axe d'une voie. lane_id 1 et -1 encadrent l'axe median."""
        signe = 1 if lane_id > 0 else -1
        rang = abs(lane_id) - 0.5
        return self.RAYON_AXE + signe * rang * self.LARGEUR_VOIE

    def waypoint_a_abscisse(self, s: float, lane_id: int) -> Waypoint:
        """Waypoint a l'abscisse curviligne `s` sur la voie `lane_id`."""
        lane_id = min(self.VOIES, key=lambda v: abs(v - lane_id))
        rayon = self._rayon_de_voie(lane_id)
        theta = s / max(rayon, 1.0)
        cx, cy = self.CENTRE
        x = cx + rayon * math.cos(theta)
        y = cy + rayon * math.sin(theta)
        # Tangente : sens de parcours oppose selon le signe de lane_id.
        sens = -1.0 if lane_id < 0 else 1.0
        yaw = math.degrees(theta + sens * math.pi / 2.0)
        return Waypoint(Transform(Location(x, y, 0.3), Rotation(yaw=yaw)),
                        self.LARGEUR_VOIE, road_id=0, lane_id=lane_id,
                        section_id=0, s=s, carte=self)

    def get_waypoint(self, location: Location, project_to_road: bool = True,
                     lane_type=LaneType.Driving) -> Optional[Waypoint]:
        cx, cy = self.CENTRE
        dx, dy = location.x - cx, location.y - cy
        rayon = math.hypot(dx, dy)
        if rayon < 1e-6:
            return None
        # Voie la plus proche en rayon.
        lane_id = min(self.VOIES, key=lambda v: abs(self._rayon_de_voie(v) - rayon))
        theta = math.atan2(dy, dx)
        s = theta * self._rayon_de_voie(lane_id)
        return self.waypoint_a_abscisse(s, lane_id)


# ---------------------------------------------------------------------------
# Monde
# ---------------------------------------------------------------------------


class WorldSettings:
    def __init__(self):
        self.synchronous_mode = False
        self.fixed_delta_seconds = None
        self.substepping = True
        self.max_substep_delta_time = 0.01
        self.max_substeps = 10


class World:
    def __init__(self, nom_carte: str = "Town04"):
        self._carte = Map(nom_carte)
        self._settings = WorldSettings()
        self._acteurs: List[Actor] = []
        self._abonnes: Dict[int, list] = {}
        self._meteo = WeatherParameters()
        self.n_ticks = 0

    def get_map(self) -> Map:
        return self._carte

    def get_settings(self) -> WorldSettings:
        s = WorldSettings()
        s.synchronous_mode = self._settings.synchronous_mode
        s.fixed_delta_seconds = self._settings.fixed_delta_seconds
        return s

    def apply_settings(self, settings: WorldSettings) -> int:
        self._settings = settings
        return 0

    def get_blueprint_library(self) -> BlueprintLibrary:
        return BlueprintLibrary()

    def set_weather(self, meteo: WeatherParameters) -> None:
        self._meteo = meteo

    def get_weather(self) -> WeatherParameters:
        return self._meteo

    def get_actors(self, ids=None) -> List[Actor]:
        return list(self._acteurs)

    def get_random_location_from_navigation(self) -> Location:
        import random
        a = random.uniform(0, 2 * math.pi)
        r = random.uniform(0, 140)
        return Location(200.0 + r * math.cos(a), 180.0 + r * math.sin(a), 0.3)

    def spawn_actor(self, blueprint: ActorBlueprint, transform: Transform,
                    attach_to: Optional[Actor] = None) -> Actor:
        acteur = Actor(blueprint, transform, self)
        if attach_to is not None:
            acteur._parent = attach_to
        self._acteurs.append(acteur)
        return acteur

    def try_spawn_actor(self, blueprint: ActorBlueprint, transform: Transform,
                        attach_to: Optional[Actor] = None) -> Optional[Actor]:
        # Simule un refus occasionnel : les vraies cartes ont des points occupés.
        for a in self._acteurs:
            if a.get_transform().location.distance(transform.location) < 3.0:
                return None
        return self.spawn_actor(blueprint, transform, attach_to)

    def tick(self, timeout: float = 10.0) -> int:
        """Avance le monde d'un pas : intégration cinématique + capteurs."""
        self.n_ticks += 1
        dt = self._settings.fixed_delta_seconds or 0.05

        for a in self._acteurs:
            if a.type_id.startswith("sensor.") or a.type_id.startswith("controller."):
                continue
            # Freinage / accélération très simplifiés, juste de quoi que la
            # vitesse évolue de façon plausible.
            c = a._controle
            v = math.sqrt(a._vitesse.x ** 2 + a._vitesse.y ** 2)
            if c.brake > 0.01:
                v = max(0.0, v - 8.0 * c.brake * dt)
            elif c.throttle > 0.01:
                v = min(40.0, v + 3.0 * c.throttle * dt)
            r = math.radians(a._tf.rotation.yaw)
            a._vitesse = Vector3D(v * math.cos(r), v * math.sin(r), 0.0)
            a._tf = Transform(
                Location(a._tf.location.x + a._vitesse.x * dt,
                         a._tf.location.y + a._vitesse.y * dt,
                         a._tf.location.z),
                Rotation(yaw=a._tf.rotation.yaw
                         + math.degrees(c.steer * v * dt * 0.3)),
            )

        self._emettre_capteurs()
        return self.n_ticks

    def _emettre_capteurs(self) -> None:
        """Fait émettre les capteurs abonnés (caméra, obstacle, collision)."""
        import numpy as np
        for sid, abonnements in list(self._abonnes.items()):
            for capteur, callback in abonnements:
                if capteur.type_id == "sensor.camera.rgb":
                    w = int(capteur.attributes.get("image_size_x", 800))
                    h = int(capteur.attributes.get("image_size_y", 600))
                    img = types.SimpleNamespace(
                        width=w, height=h,
                        raw_data=bytes(bytearray(w * h * 4)),
                    )
                    callback(img)
                elif capteur.type_id == "sensor.other.obstacle":
                    # Le capteur n'émet QUE si un obstacle existe vraiment.
                    # Émettre un mur fictif en permanence reproduisait
                    # exactement le défaut qu'on cherche à éliminer : une route
                    # vide doit rester vide, sinon le scénario « trajet A -> B
                    # sans objet » ne teste rien.
                    if getattr(self, "obstacle_fictif_m", None) is not None:
                        callback(types.SimpleNamespace(
                            distance=float(self.obstacle_fictif_m),
                            other_actor=types.SimpleNamespace(
                                type_id="static.prop.wall"),
                        ))
                # sensor.other.collision : aucun événement (pas de collision simulée)


# ---------------------------------------------------------------------------
# Traffic Manager et client
# ---------------------------------------------------------------------------


class TrafficManager:
    """Notez l'ABSENCE de `get_synchronous_mode` — comme dans le vrai CARLA.

    C'est précisément cette absence qui a fait échouer la première exécution.
    Le double la reproduit fidèlement pour que l'erreur soit rattrapée ici.
    """

    def __init__(self, port: int = 8000):
        self._port = port
        self._sync = False

    def get_port(self) -> int:
        return self._port

    def set_synchronous_mode(self, actif: bool) -> None:
        self._sync = actif

    def set_random_device_seed(self, graine: int) -> None:
        pass

    def vehicle_percentage_speed_difference(self, actor, pct: float) -> None:
        pass

    def ignore_lights_percentage(self, actor, pct: float) -> None:
        pass

    def global_percentage_speed_difference(self, pct: float) -> None:
        pass


class Client:
    def __init__(self, host: str = "localhost", port: int = 2000, worker_threads: int = 0):
        self.host, self.port = host, port
        self._world = World("Town04")
        self._tm = TrafficManager()

    def set_timeout(self, secondes: float) -> None:
        pass

    def get_server_version(self) -> str:
        return "0.9.16-fake"

    def get_client_version(self) -> str:
        return "0.9.16-fake"

    def get_world(self) -> World:
        return self._world

    def load_world(self, nom: str, reset_settings: bool = True) -> World:
        self._world = World(nom)
        return self._world

    def reload_world(self) -> World:
        return self._world

    def get_available_maps(self) -> List[str]:
        return ["/Game/Carla/Maps/" + n for n in
                ("Town01", "Town02", "Town03", "Town04", "Town05", "Town10HD")]

    def get_trafficmanager(self, port: int = 8000) -> TrafficManager:
        return self._tm

    def start_recorder(self, nom: str, additional_data: bool = False) -> str:
        return nom

    def stop_recorder(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Installation dans sys.modules
# ---------------------------------------------------------------------------


def installer() -> types.ModuleType:
    """Place ce double dans ``sys.modules["carla"]`` et le renvoie."""
    module = types.ModuleType("carla")
    for nom, obj in globals().items():
        if nom.startswith("_") or nom in ("annotations", "installer"):
            continue
        setattr(module, nom, obj)
    sys.modules["carla"] = module
    return module
