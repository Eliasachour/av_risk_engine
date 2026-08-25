"""
Pont CARLA — connexion, monde synchrone, spawn, perception.

Étape 1 de l'intégration CARLA : ce module met en place la boucle *perception*.
À chaque tick CARLA, il convertit les acteurs présents en un `ScenarioContext`
que le moteur de risque peut évaluer. Aucune décision d'ego n'est appliquée à
ce stade — c'est le rôle de l'étape 2.

**Nécessite CARLA** (`carla` Python API, version 0.9.15 recommandée). Pour les
tests hors CARLA, ce module s'importe sans erreur mais lève une `RuntimeError`
si on essaie d'instancier `CarlaBridge`.

Points d'attention CARLA 0.9.15
-------------------------------
- Mode synchrone : `fixed_delta_seconds` **entre 0.03 et 0.1** (20 Hz = 0.05).
  Descendre en dessous demande d'ajuster la sub-stepping physique.
- Traffic Manager : DOIT être en mode synchrone lui aussi, sinon les agents
  gérés par TM tournent en asynchrone et cassent la reproductibilité.
- Cleanup : sans destruction explicite des acteurs à la sortie, ils s'accumulent
  dans le monde CARLA (à voir dans `manual_control.py` — spectateurs fantômes
  à chaque relance). Le contextmanager s'en charge.
- Blueprints piétons : `walker.pedestrian.NNNN` avec NNNN de 0001 à 0048 selon
  la version. La 0001 existe partout.
"""
from __future__ import annotations

import math
from typing import List, Optional

try:
    import carla  # type: ignore
    _HAS_CARLA = True
except ImportError:
    _HAS_CARLA = False


def _carla_disponible() -> bool:
    """Vrai si le module `carla` est importable MAINTENANT.

    La vérification est faite à l'appel, et non figée au moment de l'import :
    un module importé avant que `carla` ne soit disponible resterait sinon
    inutilisable pour toute la durée du processus. C'est notamment le cas quand
    un double de test installe `carla` dans `sys.modules` après coup.
    """
    try:
        import carla  # noqa: F401
        return True
    except ImportError:
        return False

from risk_engine import (
    Agent,
    ScenarioContext,
    TypeAgent,
    assess_risk,
)
from world.extraction import ActorState, AgentObservation, refresh_context
from world.weather import weather_params


# ---------------------------------------------------------------------------
# Mapping type d'agent → blueprint CARLA
# ---------------------------------------------------------------------------

BLUEPRINTS = {
    TypeAgent.VOITURE: "vehicle.tesla.model3",
    TypeAgent.CAMION: "vehicle.carlamotors.firetruck",
    TypeAgent.CYCLISTE: "vehicle.bh.crossbike",
    TypeAgent.PIETON: "walker.pedestrian.0001",
    TypeAgent.OUVRIER: "walker.pedestrian.0002",
}

EGO_BLUEPRINT = "vehicle.tesla.model3"


# ---------------------------------------------------------------------------
# Conversions CARLA ↔ moteur
# ---------------------------------------------------------------------------


def _vitesse_ms(actor) -> float:
    """Norme du vecteur vitesse d'un acteur CARLA (m/s)."""
    v = actor.get_velocity()
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def _to_actor_state(actor) -> ActorState:
    """Convertit un `carla.Actor` en `ActorState` du moteur."""
    tr = actor.get_transform()
    return ActorState(
        x=tr.location.x,
        y=tr.location.y,
        yaw_deg=tr.rotation.yaw,
        speed_ms=_vitesse_ms(actor),
    )


# ---------------------------------------------------------------------------
# CarlaBridge : le pont réutilisable
# ---------------------------------------------------------------------------


class CarlaBridge:
    """Enveloppe CARLA pour brancher le moteur de risque.

    Cycle de vie type (mode synchrone) :

        with CarlaBridge(host="localhost", port=2000) as pont:
            pont.charger_carte("Town04")
            pont.appliquer_scenario(ctx)
            for tick in range(400):
                pont.tick()
                ctx_courant = pont.contexte_courant(ctx)
                verdict = assess_risk(ctx_courant)
                print(tick, verdict.level.name)
    """

    def __init__(self, host: str = "localhost", port: int = 2000,
                 timeout: float = 10.0, fixed_delta_seconds: float = 0.05,
                 seed: int = 0):
        if not _carla_disponible():
            raise RuntimeError(
                "Le module `carla` n'est pas importable. "
                "Installe le PythonAPI CARLA (0.9.15 ou 0.9.16) : "
                "pip install <CARLA>/PythonAPI/carla/dist/carla-0.9.1X-cpXX-*.whl"
            )
        self.client = carla.Client(host, port)
        self.client.set_timeout(timeout)
        self.world = self.client.get_world()
        self.tm = self.client.get_trafficmanager()

        # Sauvegarde des réglages d'origine pour restaurer à la sortie.
        self._settings_orig = self.world.get_settings()
        # Note : `TrafficManager` n'expose PAS de getter pour le mode synchrone
        # (seul `set_synchronous_mode` existe). On ne peut donc pas lire l'état
        # d'origine : on se contente de le remettre à False en sortie, ce qui
        # est le défaut de CARLA.

        self.fixed_delta_seconds = fixed_delta_seconds
        self.seed = seed

        # Acteurs spawnés — trackés pour destruction propre.
        self.ego = None
        self.agents: List = []
        # On garde le mapping (acteur CARLA → Agent original) : le type et la
        # profondeur mesurée ne sont pas récupérables du monde CARLA.
        self._meta: List[tuple] = []  # (TypeAgent, profondeur_mesuree)
        self._ctx_base: Optional[ScenarioContext] = None

    # --- context manager -----------------------------------------------------

    def __enter__(self):
        self._active_synchrone()
        return self

    def __exit__(self, *exc):
        self.nettoyer()

    # --- configuration du monde ---------------------------------------------

    def _active_synchrone(self) -> None:
        """Passe le monde et le TM en mode synchrone (indispensables ensemble)."""
        settings = self.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = self.fixed_delta_seconds
        # Substepping physique — les valeurs par défaut CARLA conviennent à 20 Hz.
        settings.substepping = True
        settings.max_substep_delta_time = 0.01
        settings.max_substeps = 10
        self.world.apply_settings(settings)

        self.tm.set_synchronous_mode(True)
        self.tm.set_random_device_seed(self.seed)

    def charger_carte(self, nom: str = "Town04") -> None:
        """Charge une carte (ex. 'Town04', 'Town10HD'). Reset propre du monde."""
        # `load_world` détruit tous les acteurs — on nettoie notre tracking.
        self.world = self.client.load_world(nom)
        self._active_synchrone()  # les réglages sont réappliqués sur le nouveau monde
        self.ego = None
        self.agents.clear()
        self._meta.clear()

    # --- application d'un scénario ------------------------------------------

    def appliquer_scenario(self, ctx: ScenarioContext) -> None:
        """Configure la météo et spawne l'ego + les agents selon `ctx`.

        Placement : l'ego prend un spawn point de la carte, les agents sont
        placés relativement à lui selon `distance_m`, `cap_relatif_deg` et
        `ecart_lateral_m` — même sémantique que le simulateur interne.
        """
        # Mémorisé pour que `contexte_courant()` puisse être appelé sans
        # argument : les champs invariants (météo, route, limites) viennent
        # de là, seules les poses sont rafraîchies à chaque tick.
        self._ctx_base = ctx
        # 1. Météo (visuelle uniquement — µ moteur reste piloté par etat_route).
        self.world.set_weather(carla.WeatherParameters(**weather_params(ctx)))

        bpl = self.world.get_blueprint_library()
        spawn_points = self.world.get_map().get_spawn_points()
        if not spawn_points:
            raise RuntimeError("Aucun spawn point disponible sur cette carte.")
        spawn_ego = spawn_points[0]

        # 2. Ego.
        ego_candidats = bpl.filter(EGO_BLUEPRINT) or bpl.filter("vehicle.*")
        if not ego_candidats:
            raise RuntimeError("Aucun blueprint de vehicule disponible dans cette carte.")
        ego_bp = ego_candidats[0]
        ego_bp.set_attribute("role_name", "ego")
        self.ego = self.world.spawn_actor(ego_bp, spawn_ego)
        # Vitesse initiale : lecture seule via physique — on impose via velocity.
        v_ego = ctx.vitesse_ego_kmh / 3.6
        fwd = spawn_ego.get_forward_vector()
        self.ego.set_target_velocity(carla.Vector3D(fwd.x * v_ego, fwd.y * v_ego, 0.0))

        # 3. Agents : placement RELATIF à l'ego (repère monde CARLA).
        for ag in ctx.agents:
            transform = self._transform_pour_agent(spawn_ego, ag)
            bp = self._resoudre_blueprint(bpl, ag.type_agent)
            if bp is None:
                print(f"  ! aucun blueprint disponible pour {ag.type_agent.value}, agent ignoré")
                continue
            actor = self._try_spawn(bp, transform)
            if actor is None:
                continue  # spawn refusé (collision, hors route) — on saute
            v_ag = ag.vitesse_kmh / 3.6
            fwd_ag = transform.get_forward_vector()
            actor.set_target_velocity(
                carla.Vector3D(fwd_ag.x * v_ag, fwd_ag.y * v_ag, 0.0))
            self.agents.append(actor)
            self._meta.append((ag.type_agent, ag.profondeur_mesuree))

        # 4. Un tick pour que le monde intègre les vitesses imposées.
        self.tick()

    def _resoudre_blueprint(self, bpl, type_agent):
        """Trouve un blueprint pour ce type d'agent, avec replis en cascade.

        Les identifiants de blueprints varient d'une version de CARLA à l'autre
        (certains véhicules ou piétons disparaissent, d'autres apparaissent).
        On tente le choix préféré, puis un repli par famille, puis n'importe
        quel véhicule — plutôt que de lever un IndexError sur `filter(...)[0]`.
        """
        prefere = BLUEPRINTS.get(type_agent)
        candidats = [prefere] if prefere else []
        if prefere and prefere.startswith("walker."):
            candidats += ["walker.pedestrian.0001", "walker.pedestrian.*"]
        else:
            candidats += ["vehicle.tesla.model3", "vehicle.audi.*", "vehicle.*"]

        for motif in candidats:
            try:
                trouves = bpl.filter(motif)
            except RuntimeError:
                continue
            if trouves:
                if motif != prefere:
                    print(f"  i blueprint '{prefere}' indisponible -> repli sur "
                          f"'{trouves[0].id}'")
                return trouves[0]
        return None

    def _transform_pour_agent(self, spawn_ego, ag: Agent):
        """Calcule la pose CARLA d'un agent placé relativement à l'ego.

        Convention conforme au simulateur interne :
          - distance_m devant l'ego (dans le repère ego)
          - cap_relatif_deg = orientation de l'agent (0 = même sens que l'ego)
          - ecart_lateral_m = décalage latéral positif (à gauche) ou négatif
        """
        yaw_ego = math.radians(spawn_ego.rotation.yaw)
        # Vecteurs unitaires du repère ego dans le monde CARLA.
        # CARLA : x = avant, y = droite (main gauche). On adapte.
        fx, fy = math.cos(yaw_ego), math.sin(yaw_ego)
        rx, ry = math.cos(yaw_ego + math.pi / 2), math.sin(yaw_ego + math.pi / 2)

        loc = carla.Location(
            x=spawn_ego.location.x + ag.distance_m * fx + ag.ecart_lateral_m * rx,
            y=spawn_ego.location.y + ag.distance_m * fy + ag.ecart_lateral_m * ry,
            z=spawn_ego.location.z + 0.5,  # +0.5 pour éviter de spawner sous la route
        )
        rot = carla.Rotation(
            pitch=0.0,
            yaw=spawn_ego.rotation.yaw + ag.cap_relatif_deg,
            roll=0.0,
        )
        return carla.Transform(loc, rot)

    def _try_spawn(self, bp, transform):
        """Tente un spawn ; renvoie None si CARLA le refuse (au lieu de crasher)."""
        try:
            return self.world.spawn_actor(bp, transform)
        except RuntimeError:
            return None

    # --- perception ---------------------------------------------------------

    def contexte_courant(self, ctx_base: Optional[ScenarioContext] = None) -> ScenarioContext:
        """Reconstruit un `ScenarioContext` depuis l'état actuel du monde.

        Utilise le contexte de base (météo, route, limites — invariants) et
        met à jour ego + agents à partir de leurs poses actuelles. Passe par
        le MÊME code que le simulateur interne (`refresh_context`), garantie
        de non-duplication.

        `ctx_base` est facultatif : à défaut, on reprend le contexte fourni à
        `appliquer_scenario`. Le passer explicitement sert au mode conduite
        libre, où la météo change en cours de route.
        """
        if self.ego is None:
            raise RuntimeError("Aucun ego : appelle appliquer_scenario() d'abord.")
        if ctx_base is None:
            ctx_base = self._ctx_base
        if ctx_base is None:
            raise RuntimeError(
                "Aucun contexte de base : appelle appliquer_scenario() ou passe "
                "ctx_base explicitement."
            )
        ego_state = _to_actor_state(self.ego)
        observations = []
        for actor, (type_ag, mesuree) in zip(self.agents, self._meta):
            if not actor.is_alive:
                continue
            observations.append(AgentObservation(
                state=_to_actor_state(actor),
                type_agent=type_ag,
                profondeur_mesuree=mesuree,
            ))
        return refresh_context(ctx_base, ego_state, observations)

    def tick(self) -> None:
        """Fait avancer le monde d'un pas de simulation."""
        self.world.tick()

    # --- nettoyage ----------------------------------------------------------

    def nettoyer(self) -> None:
        """Restaure les réglages d'origine et détruit les acteurs spawnés."""
        # 1. Détruire les agents.
        for actor in self.agents:
            if actor and actor.is_alive:
                try:
                    actor.destroy()
                except RuntimeError:
                    pass
        self.agents.clear()
        self._meta.clear()
        if self.ego and self.ego.is_alive:
            try:
                self.ego.destroy()
            except RuntimeError:
                pass
        self.ego = None

        # 2. Restaurer les réglages du monde et du TM.
        # Le TM est remis en asynchrone (son défaut) : impossible de lire son
        # état d'origine, CARLA n'expose pas de getter. Sans cette remise à
        # zéro, un serveur laissé en synchrone fige les prochains clients.
        try:
            self.world.apply_settings(self._settings_orig)
        except RuntimeError:
            pass
        try:
            self.tm.set_synchronous_mode(False)
        except RuntimeError:
            pass
