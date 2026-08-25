"""
Structures de données décrivant une situation de conduite.

Principe directeur : ce module ne dépend PAS de CARLA. Le moteur de risque
travaille uniquement sur ces dataclasses, ce qui le rend testable sans lancer
le simulateur. L'adaptateur CARLA (paquet `world/`, à venir) aura pour seule
tâche de remplir un ScenarioContext à partir de l'état du monde simulé.

Unités : vitesses en km/h (comme dans le tableau de scénarios), distances en m,
accélérations en m/s², caps en degrés (0 = même sens, 90 = croisement,
180 = face-à-face).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class EtatRoute(Enum):
    SEC = "sec"
    MOUILLE = "mouille"
    NEIGEUX = "neigeux"
    VERGLAS = "verglas"


class Meteo(Enum):
    CLAIR = "clair"
    PLUIE = "pluie"
    BROUILLARD = "brouillard"
    NEIGE = "neige"


class Heure(Enum):
    JOUR = "jour"
    NUIT = "nuit"


class Geometrie(Enum):
    DROITE = "droite"
    VIRAGE = "virage"


class TypeRoute(Enum):
    AUTOROUTE = "autoroute"
    NATIONALE = "nationale"
    DEPARTEMENTALE = "departementale"
    URBAIN = "urbain"


class TypeAgent(Enum):
    VOITURE = "voiture"
    CAMION = "camion"
    CYCLISTE = "cycliste"
    PIETON = "pieton"
    OUVRIER = "ouvrier"


@dataclass
class Agent:
    """Un usager de la route (entité dynamique au sens ISO 34503)."""
    type_agent: TypeAgent
    vitesse_kmh: float
    distance_m: float
    cap_relatif_deg: float          # 0 = même sens, 90 = croisement, 180 = face-à-face
    acceleration_ms2: float = 0.0
    # True  -> profondeur MESURÉE (LiDAR/radar, temps de vol)
    # False -> profondeur INFÉRÉE (caméra) -> pénalité d'incertitude appliquée
    profondeur_mesuree: bool = True
    # Position latérale initiale (m) : 0 = sur l'axe de l'ego, > 0 ou < 0 = décalé
    # d'un côté. Un agent décalé et en croisement se dirige vers l'axe (traversée).
    ecart_lateral_m: float = 0.0

    def __post_init__(self) -> None:
        if self.distance_m < 0:
            raise ValueError("distance_m doit être >= 0")
        if self.vitesse_kmh < 0:
            raise ValueError("vitesse_kmh doit être >= 0")


@dataclass
class ScenarioContext:
    """État instantané d'une situation, regroupant les 13 paramètres du tableau."""
    # --- véhicule ego ---
    vitesse_ego_kmh: float
    # --- contexte routier ---
    type_route: TypeRoute = TypeRoute.NATIONALE
    geometrie: Geometrie = Geometrie.DROITE
    limite_vitesse_kmh: float = 50.0
    zone_travaux: bool = False
    # --- conditions environnementales ---
    etat_route: EtatRoute = EtatRoute.SEC
    meteo: Meteo = Meteo.CLAIR
    heure: Heure = Heure.JOUR
    visibilite_m: float = 500.0
    # --- agents (entités dynamiques) ---
    agents: List[Agent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.vitesse_ego_kmh < 0:
            raise ValueError("vitesse_ego_kmh doit être >= 0")
