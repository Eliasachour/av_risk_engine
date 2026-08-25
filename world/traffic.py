"""
Gestion du trafic autonome et des piétons IA en mode conduite libre, 
avec gestion de 4 scénarios de densité et de comportements stochastiques (S4).
"""
from __future__ import annotations

import random
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict

try:
    import carla  # type: ignore
    _HAS_CARLA = True
except ImportError:
    _HAS_CARLA = False


# Blueprints à exclure : problèmes connus en 0.9.15
_VEHICULES_EXCLUS = {"vehicle.tesla.cybertruck"}   # collision box étrange
_PIETONS_EXCLUS = {"walker.pedestrian.0022"}       # peut ne pas exister


class TypeScenario(Enum):
    NORMAL = 1
    PEU_DENSE = 2
    DENSE = 3
    IMPREVISIBLE = 4

@dataclass
class ScenarioConfig:
    num_vehicules: int
    num_pietons: int
    vitesse_variation_min: float
    vitesse_variation_max: float
    distance_securite_min: float
    distance_securite_max: float
    probabilite_changement_voie: float

@dataclass
class Personnalite:
    nom: str
    vitesse_delta: float
    distance_securite: float
    changement_voie: float
    reaction_retard: bool
    agressivite: float


class GestionnaireTrafic:
    """Peuple le monde CARLA de véhicules et piétons IA autour de l'ego."""

    def __init__(self, world, traffic_manager, scenario_id: int = 1, seed: int = 42):
        if not _HAS_CARLA:
            raise RuntimeError("carla n'est pas installé.")
        self.world = world
        self.tm = traffic_manager
        self.seed = seed
        self.type_scenario = TypeScenario(scenario_id)

        # Configuration stricte des 4 scénarios
        self.configs = {
            TypeScenario.NORMAL: ScenarioConfig(15, 0, 0.0, 5.0, 4.0, 5.0, 5.0),
            TypeScenario.PEU_DENSE: ScenarioConfig(40, 15, -10.0, 10.0, 3.0, 4.5, 15.0),
            TypeScenario.DENSE: ScenarioConfig(100, 40, -20.0, 5.0, 1.5, 3.0, 40.0),
            TypeScenario.IMPREVISIBLE: ScenarioConfig(100, 40, 0.0, 0.0, 0.0, 0.0, 0.0)
        }
        
        self.config_actuelle = self.configs[self.type_scenario]
        self.n_vehicules = self.config_actuelle.num_vehicules
        self.n_pietons = self.config_actuelle.num_pietons

        self.vehicules: List["carla.Actor"] = []
        self.walkers: List["carla.Actor"] = []
        self.controleurs_walkers: List["carla.Actor"] = []
        
        # Variables pour le Scénario 4
        self.personnalites_attribuees: Dict[int, Personnalite] = {} 
        self.evenements_actifs: Dict[int, float] = {}
        self.personnalites_types = [
            Personnalite("Prudent", 15.0, 5.0, 5.0, False, 0.1),
            Personnalite("Normal", 0.0, 3.0, 20.0, False, 0.5),
            Personnalite("Presse", -15.0, 1.5, 60.0, False, 0.8),
            Personnalite("Distrait", 5.0, 4.0, 10.0, True, 0.3),
        ]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.nettoyer()

    # -------------------------------------------------------------- spawn

    def spawn_autour_de(self, ego, rayon_m: float = 80.0, centre=None) -> None:
        """Spawn tous les acteurs dans un rayon autour de l'ego."""
        random.seed(self.seed)
        self.tm.set_random_device_seed(self.seed)
        
        if centre is None:
            centre = ego.get_transform().location
            
        print(f"--- Démarrage du scénario : {self.type_scenario.name} ---")
        self._spawn_vehicules(centre, rayon_m)
        self._spawn_pietons(centre, rayon_m)

    def _appliquer_personnalite_base(self, vehicule, p: Personnalite):
        self.tm.vehicle_percentage_speed_difference(vehicule, p.vitesse_delta)
        self.tm.distance_to_leading_vehicle(vehicule, p.distance_securite)
        self.tm.random_left_lanechange_percentage(vehicule, p.changement_voie)
        self.tm.random_right_lanechange_percentage(vehicule, p.changement_voie)
        self.tm.ignore_vehicles_percentage(vehicule, 0.0)

    def _spawn_vehicules(self, ego_loc, rayon_m: float) -> None:
        bp_lib = self.world.get_blueprint_library()
        bps = [bp for bp in bp_lib.filter("vehicle.*")
               if bp.id not in _VEHICULES_EXCLUS]
        if not bps:
            return

        spawn_points = self.world.get_map().get_spawn_points()
        candidats = [sp for sp in spawn_points if 8.0 < sp.location.distance(ego_loc) < rayon_m]
        
        if len(candidats) < self.n_vehicules:
            candidats = [sp for sp in spawn_points if sp.location.distance(ego_loc) > 8.0]
            
        random.shuffle(candidats)
        candidats = candidats[: self.n_vehicules]

        for sp in candidats:
            bp = random.choice(bps)
            bp.set_attribute("role_name", "autopilot")
            if bp.has_attribute("color"):
                couleurs = bp.get_attribute("color").recommended_values
                if couleurs:
                    bp.set_attribute("color", random.choice(couleurs))
                    
            actor = self.world.try_spawn_actor(bp, sp)
            if actor is not None:
                actor.set_autopilot(True, self.tm.get_port())
                
                if self.type_scenario != TypeScenario.IMPREVISIBLE:
                    var_vit = random.uniform(self.config_actuelle.vitesse_variation_min, self.config_actuelle.vitesse_variation_max)
                    dist_sec = random.uniform(self.config_actuelle.distance_securite_min, self.config_actuelle.distance_securite_max)
                    self.tm.vehicle_percentage_speed_difference(actor, var_vit)
                    self.tm.distance_to_leading_vehicle(actor, dist_sec)
                    self.tm.random_left_lanechange_percentage(actor, self.config_actuelle.probabilite_changement_voie)
                    self.tm.random_right_lanechange_percentage(actor, self.config_actuelle.probabilite_changement_voie)
                else:
                    p = random.choices(self.personnalites_types, weights=[30, 40, 15, 15], k=1)[0]
                    self.personnalites_attribuees[actor.id] = p
                    self._appliquer_personnalite_base(actor, p)

                self.vehicules.append(actor)

        print(f"  -> {len(self.vehicules)} véhicules IA spawn")

    def _spawn_pietons(self, ego_loc, rayon_m: float) -> None:
        """Logique de spawn des piétons conservée à l'identique de l'original."""
        bp_lib = self.world.get_blueprint_library()
        bps = [bp for bp in bp_lib.filter("walker.pedestrian.*")
               if bp.id not in _PIETONS_EXCLUS]
        if not bps:
            return

        try:
            bp_controleur = bp_lib.find("controller.ai.walker")
        except (RuntimeError, IndexError):
            print("  ! controller.ai.walker introuvable : pietons non spawnes")
            return

        points = []
        essais_max = max(200, self.n_pietons * 40)
        essais = 0
        while len(points) < self.n_pietons and essais < essais_max:
            essais += 1
            loc = self.world.get_random_location_from_navigation()
            if loc is None:
                continue
            if loc.distance(ego_loc) < rayon_m:
                points.append(loc)
                
        if len(points) < self.n_pietons:
            manque = self.n_pietons - len(points)
            for _ in range(manque * 20):
                if len(points) >= self.n_pietons:
                    break
                loc = self.world.get_random_location_from_navigation()
                if loc is not None:
                    points.append(loc)

        spawn_walker_batch = []
        for loc in points:
            bp = random.choice(bps)
            if bp.has_attribute("is_invincible"):
                bp.set_attribute("is_invincible", "false")
            tf = carla.Transform(loc)
            actor = self.world.try_spawn_actor(bp, tf)
            if actor is not None:
                self.walkers.append(actor)
                spawn_walker_batch.append(actor)

        for walker in spawn_walker_batch:
            ctrl = self.world.try_spawn_actor(bp_controleur, carla.Transform(), attach_to=walker)
            if ctrl is not None:
                self.controleurs_walkers.append(ctrl)

        self.world.tick()

        for ctrl in self.controleurs_walkers:
            ctrl.start()
            dest = self.world.get_random_location_from_navigation()
            if dest is not None:
                ctrl.go_to_location(dest)
            ctrl.set_max_speed(random.uniform(1.0, 1.8))

        print(f"  -> {len(self.walkers)} piétons spawn avec contrôleurs AI")

    def tick(self, temps_actuel: float):
        """Gère les événements imprévisibles du Scénario 4 au fil du temps."""
        if self.type_scenario != TypeScenario.IMPREVISIBLE or not self.personnalites_attribuees:
            return

        vehicules_a_restaurer = []
        for vid, temps_fin in self.evenements_actifs.items():
            if temps_actuel >= temps_fin:
                vehicules_a_restaurer.append(vid)
        
        for vid in vehicules_a_restaurer:
            del self.evenements_actifs[vid]
            vehicule = self.world.get_actor(vid)
            if vehicule:
                p = self.personnalites_attribuees[vid]
                self._appliquer_personnalite_base(vehicule, p)

        for vehicule in self.vehicules:
            if vehicule.id in self.evenements_actifs or not vehicule.is_alive:
                continue

            p = self.personnalites_attribuees.get(vehicule.id)
            if not p:
                continue
            
            if random.random() < 0.001 * p.agressivite:
                type_evenement = random.choice(["freinage_soudain", "insertion_forcee", "hesitation"])
                duree_evenement = random.uniform(2.0, 5.0)
                self.evenements_actifs[vehicule.id] = temps_actuel + duree_evenement

                if type_evenement == "freinage_soudain":
                    self.tm.vehicle_percentage_speed_difference(vehicule, 80.0) 
                
                elif type_evenement == "insertion_forcee" and p.agressivite > 0.5:
                    self.tm.distance_to_leading_vehicle(vehicule, 0.5) 
                    self.tm.force_lane_change(vehicule, random.choice([True, False]))
                
                elif type_evenement == "hesitation" and p.reaction_retard:
                    self.tm.vehicle_percentage_speed_difference(vehicule, 40.0)
                    self.tm.random_left_lanechange_percentage(vehicule, 0.0)
                    self.tm.random_right_lanechange_percentage(vehicule, 0.0)

    # ---------------------------------------------------------- nettoyage

    def nettoyer(self) -> None:
        """Arrête les contrôleurs, détruit tous les acteurs spawn."""
        for ctrl in self.controleurs_walkers:
            if ctrl.is_alive:
                try:
                    ctrl.stop()
                    ctrl.destroy()
                except Exception:
                    pass
        for actor in (*self.walkers, *self.vehicules):
            if actor.is_alive:
                try:
                    actor.destroy()
                except Exception:
                    pass
        self.controleurs_walkers = []
        self.walkers = []
        self.vehicules = []