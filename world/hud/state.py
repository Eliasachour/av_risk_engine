"""État courant du HUD — mis à jour à chaque tick CARLA."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from risk_engine import RiskLevel


@dataclass
class HUDState:
    """Ce que le HUD affiche à un instant t.

    Le point d'entrée CARLA construit un nouveau ``HUDState`` à chaque tick à
    partir du contexte, du verdict du moteur et de la commande recommandée,
    puis le passe à ``HUD.rendre``. Découpler ainsi l'état du rendu rend le
    HUD testable et permet de brancher plusieurs rendus (Pygame, futur web…).

    Attributs
    ---------
    t : float
        Temps simulé en secondes depuis le début de la session.
    niveau : RiskLevel
        Niveau global du moteur à cet instant.
    vitesse_ego_kmh : float
        Vitesse mesurée de l'ego (via CARLA), en km/h.
    freinage : bool
        Vrai si un frein > 5 % est appliqué (déclenche le badge FREIN).
    agent_critique : dict | None
        Le pire agent parmi les détectés, avec ses métriques (type, distance,
        ttc, thw, drac, rss, niveau). None si aucun agent n'est proche.
    n_agents : int
        Nombre total d'agents dans la scène.
    diagnostic : str
        Message court affiché dans le bandeau inférieur.
    mu_g : float | None
        Adhérence disponible (m/s²) — utilisée par la jauge DRAC.
    mode_ctrl : str
        "nominal" | "proportionnel" | "physique" | "pause" | "off".
    agents_detail : list[dict]
        Liste de tous les agents avec leurs métriques (panneau latéral gauche).
    v_cible_kmh : float
        Vitesse cible de l'ACC (affichée sous la vitesse ego).
    """
    t: float
    niveau: RiskLevel
    vitesse_ego_kmh: float
    freinage: bool
    agent_critique: Optional[dict]
    n_agents: int
    diagnostic: str
    mu_g: Optional[float] = None
    mode_ctrl: str = "off"
    agents_detail: List[dict] = field(default_factory=list)
    v_cible_kmh: float = 0.0
    # --- Champs conduite libre ---
    mode_conduite: str = "scenario"       # "scenario" | "libre"
    assistance: str = ""                  # "" | "EVAL" | "ALERTE" | "AEB"
    aeb_engage: bool = False              # AEB actif (freinage automatique)
    alerte_msg: str = ""                  # message d'alerte à afficher
    rayon_perception_m: float = 60.0
    demi_angle_perception_deg: float = 60.0
    meteo_resume: str = ""               # ligne météo affichée en bas
    # --- Recommandation d'action (mode apprentissage) ---
    reco_message: str = ""               # « Ralentissez de 15 km/h (70 -> 55) »
    reco_justification: str = ""         # la raison physique
    reco_urgence: int = 0                # 0 aucune · 1 anticiper · 2 agir · 3 urgent
    facteur_temps_reel: float = 0.0      # temps simulé / temps réel (1.0 = juste)
    fps: float = 0.0
    # --- Contexte routier lu depuis CARLA ---
    limite_vitesse_kmh: int = 0
    geometrie: str = ""                  # "droite" | "virage"
    feu: str = "aucun"                   # "rouge" | "jaune" | "vert" | "aucun"
    hors_voie: bool = False
    # --- Obstacles statiques et collisions ---
    obstacle_statique_m: Optional[float] = None   # distance au mur devant
    n_collisions: int = 0
    collision_recente: bool = False
    # --- Métriques du verdict global (agent le plus critique) ---
    metriques: dict = field(default_factory=dict)  # {nom: (valeur, unite, niveau)}
    metrique_decisive: str = ""
    ratio_rss: Optional[float] = None
    ttc_effectif: Optional[float] = None
    marge_contextuelle: Optional[float] = None
    corroboration: Optional[float] = None

