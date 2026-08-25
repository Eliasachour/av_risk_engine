"""
Capteurs d'environnement CARLA — ce que la perception d'acteurs ne voit pas.

Le module `perception_oracle` ne remonte que les **acteurs** (véhicules,
piétons). Or la carte CARLA contient bien d'autres sources de danger qui ne
sont pas des acteurs : murs, glissières, façades, poteaux, terre-plein. Foncer
dans un mur laissait donc le moteur en SAFE — un trou majeur.

Ce module comble ce trou et enrichit le contexte transmis au moteur :

- ``DetecteurObstacle``  — capteur ``sensor.other.obstacle`` : distance au
  premier obstacle devant, y compris la géométrie statique de la carte.
- ``DetecteurCollision`` — capteur ``sensor.other.collision`` : impacts réels,
  avec l'intensité. Indispensable pour valider (et pour le mémoire).
- ``contexte_route``     — lit la carte et le véhicule pour renseigner la
  limite de vitesse réelle, la géométrie (ligne droite / virage) et l'état du
  feu tricolore. Ces champs étaient jusqu'ici figés dans le formulaire.

Principe directeur : **ne rien inventer**. Chaque grandeur transmise au moteur
provient d'une mesure CARLA, pas d'une valeur par défaut choisie à la main.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from risk_engine import Agent, TypeAgent
from risk_engine.context import Geometrie


# ---------------------------------------------------------------------------
# Obstacles statiques
# ---------------------------------------------------------------------------


#: Fragments de `type_id` correspondant à la chaussée et au décor traversable.
#: Le capteur d'obstacle les remonte comme n'importe quel obstacle : sans ce
#: filtre, l'ego « voit » le bitume sous ses roues.
_SURFACES_IGNOREES = (
    "road", "roadline", "sidewalk", "ground", "terrain", "water",
    "vegetation", "sky", "rail", "guardrail_flat",
)

#: Distance en deçà de laquelle une détection est tenue pour un artefact.
#: Le capteur est monté à 2,2 m du centre de l'ego : un retour à moins de 3 m
#: correspond au pare-chocs, au sol, ou à un rebond — pas à un obstacle utile.
DISTANCE_MIN_CREDIBLE_M = 3.0

#: Nombre de détections consécutives avant de croire à un obstacle.
#: Un retour isolé est presque toujours un artefact (bosse, joint de chaussée).
DETECTIONS_AVANT_CONFIANCE = 3


@dataclass
class InfoObstacle:
    """Dernière détection du capteur d'obstacle."""
    distance_m: float = math.inf
    est_statique: bool = False
    etiquette: str = ""
    t_detection: float = -1e9

    def valide(self, t_courant: float, peremption_s: float = 0.4) -> bool:
        """Une détection ne vaut que quelques dixièmes de seconde.

        Le capteur ne signale rien quand la voie est libre : sans péremption,
        on garderait indéfiniment un obstacle qui n'existe plus.
        """
        return (t_courant - self.t_detection) <= peremption_s


class DetecteurObstacle:
    """Capteur ``sensor.other.obstacle`` monté à l'avant de l'ego.

    Contrairement à la perception d'acteurs, ce capteur détecte aussi les
    **maillages statiques** de la carte (murs, façades, glissières). C'est lui
    qui permet au moteur de voir un mur.

    Le résultat est exposé sous forme d'``Agent`` immobile via
    ``agent_equivalent()``, pour que le moteur le traite comme n'importe quel
    autre conflit — sans avoir à connaître l'existence des murs.
    """

    def __init__(self, world, ego, portee_m: float = 60.0,
                 rayon_m: float = 0.45):
        import carla
        bp = world.get_blueprint_library().find("sensor.other.obstacle")
        bp.set_attribute("distance", str(portee_m))
        # ATTENTION au rayon : le capteur teste une CAPSULE, pas un rayon. Avec
        # un rayon de 1,2 m et un capteur à z = 0,9 m, la capsule descend à
        # z = -0,3 m, sous la chaussée — le capteur touchait donc le bitume en
        # permanence, à distance nulle, et le moteur voyait un obstacle
        # immobile collé au pare-chocs. D'où un CRITICAL perpétuel.
        # Rayon réduit et capteur relevé : la capsule reste au-dessus du sol.
        bp.set_attribute("hit_radius", str(rayon_m))
        bp.set_attribute("only_dynamics", "False")
        bp.set_attribute("sensor_tick", "0.0")
        # Le capteur émet une capsule de rayon `rayon_m` centrée sur ce point.
        # Elle NE DOIT PAS atteindre le sol : avec un rayon de 1,2 m à
        # z = 1,0 m, elle descendait à z = -0,2 m et détectait la chaussée à
        # chaque tick. On monte le capteur et on resserre le rayon.
        tf = carla.Transform(carla.Location(x=2.2, z=1.4))
        self.sensor = world.spawn_actor(bp, tf, attach_to=ego)
        self._world = world
        self._ego = ego
        self._offset_capteur_m = 2.2
        self.info = InfoObstacle()
        self._t_courant = 0.0
        self._consecutives = 0
        self._rejets = {"proche": 0, "surface": 0, "acteur": 0, "hors_voie": 0}
        self.sensor.listen(self._on_event)

    def maj_temps(self, t: float) -> None:
        """À appeler chaque tick : sert à dater et périmer les détections."""
        self._t_courant = t

    def _on_event(self, event) -> None:
        """Filtre les retours du capteur avant de les croire.

        Quatre rejets successifs, du plus fréquent au plus rare :

        1. **Trop proche** — sous ``DISTANCE_MIN_CREDIBLE_M``, c'est le sol,
           le pare-chocs ou un rebond, jamais un obstacle exploitable.
        2. **Surface de roulement** — chaussée, trottoir, marquage, végétation :
           l'ego roule dessus ou à côté, ce ne sont pas des obstacles.
        3. **Acteur déjà suivi** — véhicules et piétons sont vus par la
           perception d'acteurs ; les compter deux fois fausserait le verdict.
        4. **Détection isolée** — il faut ``DETECTIONS_AVANT_CONFIANCE`` retours
           consécutifs pour qu'un obstacle soit transmis au moteur.
        """
        distance = float(event.distance)
        type_id = (getattr(event.other_actor, "type_id", "") or "").lower()

        # 1. Trop proche : artefact.
        if distance < DISTANCE_MIN_CREDIBLE_M:
            self._rejets["proche"] += 1
            self._consecutives = 0
            return

        # 2. Surface de roulement ou décor traversable.
        if any(mot in type_id for mot in _SURFACES_IGNOREES):
            self._rejets["surface"] += 1
            self._consecutives = 0
            return

        # 3. Acteur déjà pris en compte ailleurs.
        if type_id.startswith("vehicle.") or type_id.startswith("walker."):
            self._rejets["acteur"] += 1
            self._consecutives = 0
            return

        # 4. Hors de la trajectoire carrossable : decor de bord de route.
        if not self._dans_le_couloir(distance):
            self._rejets["hors_voie"] += 1
            self._consecutives = 0
            return

        # 5. Confirmation sur plusieurs ticks.
        self._consecutives += 1
        if self._consecutives < DETECTIONS_AVANT_CONFIANCE:
            return

        self.info = InfoObstacle(
            distance_m=distance,
            est_statique=True,
            etiquette=type_id or "geometrie_statique",
            t_detection=self._t_courant,
        )

    def _dans_le_couloir(self, distance: float) -> bool:
        """L'obstacle détecté est-il sur la trajectoire carrossable de l'ego ?

        Un capteur d'obstacle émet un rayon **droit devant**, or la route
        tourne. En courbe, ce rayon quitte le bitume et touche ce qui se trouve
        à l'extérieur du virage : glissière, façade, talus. Ce sont de vrais
        objets, mais ils ne sont pas sur le chemin du véhicule — les signaler
        produit une alerte permanente dès que la route n'est pas rectiligne.

        On reconstruit donc le point d'impact et on vérifie qu'il tombe sur une
        voie carrossable, à moins d'une demi-largeur de voie de son axe. Sinon,
        l'obstacle est du décor de bord de route et n'entre pas dans
        l'évaluation.
        """
        try:
            import carla

            tf = self._ego.get_transform()
            avant = tf.get_forward_vector()
            portee = self._offset_capteur_m + distance
            impact = carla.Location(
                x=tf.location.x + avant.x * portee,
                y=tf.location.y + avant.y * portee,
                z=tf.location.z + 1.0,
            )
            wp = self._world.get_map().get_waypoint(
                impact, project_to_road=False, lane_type=carla.LaneType.Driving)
            if wp is None:
                return False        # hors de toute voie carrossable
            ecart = impact.distance(wp.transform.location)
            return ecart <= (wp.lane_width / 2.0 + 0.5)
        except (RuntimeError, AttributeError):
            # En cas de doute sur l'API, on conserve la détection : mieux vaut
            # une alerte de trop qu'un obstacle ignoré.
            return True

    def diagnostic(self) -> str:
        """Compte des rejets, pour comprendre ce que voit le capteur."""
        r = self._rejets
        return (f"obstacle: rejets proche={r['proche']} surface={r['surface']} "
                f"acteur={r['acteur']} hors_voie={r['hors_voie']}")

    def agent_equivalent(self, marge_m: float = 0.0) -> Optional[Agent]:
        """Traduit l'obstacle courant en ``Agent`` immobile, ou None.

        Le type retenu est ``VOITURE`` : son facteur de vulnérabilité vaut 1,0
        (neutre), ce qui correspond bien à un obstacle rigide immobile. Utiliser
        ``PIETON`` (facteur 1,5) surestimerait le risque ; il n'existe pas de
        type « obstacle » dans le moteur, et en ajouter un aurait invalidé la
        calibration des 24 scénarios.
        """
        if not self.info.valide(self._t_courant):
            return None
        d = self.info.distance_m - marge_m
        if d < DISTANCE_MIN_CREDIBLE_M:
            # Ne jamais fabriquer un obstacle collé au pare-chocs : c'était le
            # comportement qui rendait le mode conduite libre inutilisable.
            return None
        return Agent(
            type_agent=TypeAgent.VOITURE,
            vitesse_kmh=0.0,          # un mur ne bouge pas
            distance_m=d,
            cap_relatif_deg=0.0,      # droit devant
            acceleration_ms2=0.0,
            ecart_lateral_m=0.0,      # dans la voie, par construction
            profondeur_mesuree=True,  # mesure directe du capteur
        )

    def detruire(self) -> None:
        if self.sensor is not None and self.sensor.is_alive:
            self.sensor.stop()
            self.sensor.destroy()
            self.sensor = None


# ---------------------------------------------------------------------------
# Collisions
# ---------------------------------------------------------------------------


@dataclass
class EvenementCollision:
    t: float
    avec: str
    intensite: float


class DetecteurCollision:
    """Capteur ``sensor.other.collision``.

    Sans lui, une collision passait totalement inaperçue : l'ego traversait
    ou rebondissait sans que rien ne soit noté. C'est pourtant *la* mesure de
    référence pour valider un système de sécurité.
    """

    def __init__(self, world, ego):
        import carla
        bp = world.get_blueprint_library().find("sensor.other.collision")
        self.sensor = world.spawn_actor(bp, carla.Transform(), attach_to=ego)
        self.evenements: List[EvenementCollision] = []
        self._t_courant = 0.0
        self.sensor.listen(self._on_event)

    def maj_temps(self, t: float) -> None:
        self._t_courant = t

    def _on_event(self, event) -> None:
        imp = event.normal_impulse
        intensite = math.sqrt(imp.x ** 2 + imp.y ** 2 + imp.z ** 2)
        # CARLA émet plusieurs événements pour un même contact prolongé :
        # on regroupe ce qui survient dans la même demi-seconde.
        if self.evenements and (self._t_courant - self.evenements[-1].t) < 0.5:
            self.evenements[-1].intensite = max(self.evenements[-1].intensite, intensite)
            return
        self.evenements.append(EvenementCollision(
            t=self._t_courant,
            avec=getattr(event.other_actor, "type_id", "inconnu"),
            intensite=intensite,
        ))

    @property
    def nombre(self) -> int:
        return len(self.evenements)

    def derniere(self) -> Optional[EvenementCollision]:
        return self.evenements[-1] if self.evenements else None

    def collision_recente(self, peremption_s: float = 2.0) -> bool:
        d = self.derniere()
        return d is not None and (self._t_courant - d.t) <= peremption_s

    def detruire(self) -> None:
        if self.sensor is not None and self.sensor.is_alive:
            self.sensor.stop()
            self.sensor.destroy()
            self.sensor = None


# ---------------------------------------------------------------------------
# Contexte routier lu depuis la carte
# ---------------------------------------------------------------------------


@dataclass
class ContexteRoute:
    """Ce que la carte et le véhicule disent de la situation courante."""
    limite_vitesse_kmh: int = 50
    geometrie: Geometrie = Geometrie.DROITE
    feu: str = "aucun"          # "rouge" | "jaune" | "vert" | "aucun"
    hors_voie: bool = False     # l'ego n'est plus sur une voie carrossable
    courbure_deg: float = 0.0   # écart de cap sur l'horizon d'anticipation


def contexte_route(world, ego, horizon_m: float = 25.0) -> ContexteRoute:
    """Lit la limite de vitesse, la géométrie et le feu tricolore.

    Ces trois grandeurs étaient auparavant figées par le formulaire — donc
    fausses dès que l'ego changeait de rue. Les lire à chaque tick rend le
    contexte transmis au moteur conforme à la réalité simulée.
    """
    import carla

    res = ContexteRoute()

    # 1. Limite de vitesse réelle du tronçon (panneaux de la carte).
    try:
        limite = int(round(ego.get_speed_limit()))
        if limite > 0:
            res.limite_vitesse_kmh = limite
    except (RuntimeError, AttributeError):
        pass

    # 2. Feu tricolore : uniquement si l'ego est effectivement à un feu.
    try:
        if ego.is_at_traffic_light():
            etat = ego.get_traffic_light_state()
            res.feu = {
                carla.TrafficLightState.Red: "rouge",
                carla.TrafficLightState.Yellow: "jaune",
                carla.TrafficLightState.Green: "vert",
            }.get(etat, "aucun")
    except (RuntimeError, AttributeError):
        pass

    # 3. Géométrie : on compare le cap de la voie ici et à l'horizon.
    try:
        carte = world.get_map()
        tf = ego.get_transform()
        wp = carte.get_waypoint(tf.location, project_to_road=True,
                                lane_type=carla.LaneType.Driving)
        if wp is None:
            res.hors_voie = True
        else:
            # Hors voie si l'ego s'est éloigné du centre de la voie de plus
            # que sa demi-largeur plus une marge.
            ecart = tf.location.distance(wp.transform.location)
            res.hors_voie = ecart > (wp.lane_width / 2.0 + 1.5)

            suivants = wp.next(horizon_m)
            if suivants:
                d_yaw = suivants[0].transform.rotation.yaw - wp.transform.rotation.yaw
                d_yaw = (d_yaw + 180.0) % 360.0 - 180.0   # ramener dans [-180, 180]
                res.courbure_deg = abs(d_yaw)
                # 12 degres sur 25 m correspond a un rayon de ~120 m :
                # au-dela, on parle bien d'un virage et non d'une inflexion.
                if res.courbure_deg >= 12.0:
                    res.geometrie = Geometrie.VIRAGE
    except (RuntimeError, AttributeError):
        pass

    return res
