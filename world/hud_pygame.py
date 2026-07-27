"""
HUD Pygame minimaliste pour CARLA — étape 1.

Affiche en temps réel :
  - Vue caméra RGB de l'ego (fond plein écran).
  - Bandeau supérieur : niveau global (fond coloré), vitesse ego, temps sim.
  - Panneau latéral : 4 métriques principales (TTC, DRAC, RSS, niveau) pour
    l'agent le plus critique.
  - Bandeau alerte en bas si CRITICAL.

Commandes : ESC pour quitter, ESPACE pour pause, R pour reset (à venir).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

try:
    import pygame  # type: ignore
    import numpy as np
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False

from risk_engine import RiskAssessment, RiskLevel


# --- Palette (thème clair cohérent avec l'interface web) ---
COULEURS = {
    RiskLevel.SAFE:     {"bg": (230, 244, 234), "fg": (27, 94, 32),  "strong": (46, 125, 50)},
    RiskLevel.WATCH:    {"bg": (255, 248, 225), "fg": (109, 82, 0),  "strong": (249, 168, 37)},
    RiskLevel.DANGER:   {"bg": (255, 224, 178), "fg": (122, 61, 0),  "strong": (239, 108, 0)},
    RiskLevel.CRITICAL: {"bg": (255, 205, 210), "fg": (138, 28, 28), "strong": (198, 40, 40)},
}
BLANC = (255, 255, 255)
NOIR = (26, 31, 46)
GRIS = (90, 100, 120)
GRIS_CLAIR = (228, 232, 238)


@dataclass
class HUDState:
    """État courant à afficher dans le HUD (mis à jour à chaque tick)."""
    t: float
    niveau: RiskLevel
    vitesse_ego_kmh: float
    freinage: bool
    agent_critique: Optional[dict]     # {"type", "distance", "ttc", "drac", "niveau"}
    n_agents: int
    diagnostic: str                    # message court (mode, avertissement)


class HUD:
    """Fenêtre Pygame + rendu HUD.

    Utilisation :

        hud = HUD(largeur=1280, hauteur=720)
        hud.demarrer()
        while hud.actif():
            hud.attacher_image_camera(frame_rgb_np_array)   # optionnel
            hud.mettre_a_jour(state)
            hud.rendre()
        hud.fermer()
    """

    def __init__(self, largeur: int = 1280, hauteur: int = 720):
        if not _HAS_PYGAME:
            raise RuntimeError("Pygame n'est pas installé. `pip install pygame numpy`.")
        self.largeur = largeur
        self.hauteur = hauteur
        self.screen = None
        self.font_titre = None
        self.font_grand = None
        self.font_moyen = None
        self.font_petit = None
        self.font_mono = None
        self.clock = None
        self.image_camera_surface: Optional["pygame.Surface"] = None
        self.pause = False
        self._quitter = False
        self._t_critical_start: Optional[float] = None

    def demarrer(self) -> None:
        pygame.init()
        pygame.display.set_caption("AV Risk Engine — CARLA HUD")
        self.screen = pygame.display.set_mode((self.largeur, self.hauteur))
        self.clock = pygame.time.Clock()
        self.font_titre = pygame.font.SysFont("Arial", 12, bold=True)
        self.font_grand = pygame.font.SysFont("Arial", 36, bold=True)
        self.font_moyen = pygame.font.SysFont("Arial", 18, bold=True)
        self.font_petit = pygame.font.SysFont("Arial", 13)
        self.font_mono = pygame.font.SysFont("Courier", 14, bold=True)

    def attacher_image_camera(self, image_rgb) -> None:
        """Attache l'image caméra CARLA (numpy array H×W×3 en RGB) à afficher en fond."""
        if image_rgb is None:
            return
        # CARLA fournit du BGRA, on suppose ici RGB déjà converti.
        surface = pygame.image.frombuffer(image_rgb.tobytes(), image_rgb.shape[1::-1], "RGB")
        # Ajuster à la zone de la caméra (largeur totale moins panneau latéral 320px)
        zone_largeur = self.largeur - 320
        zone_hauteur = self.hauteur - 100  # moins bandeau supérieur (60) + inférieur (40)
        self.image_camera_surface = pygame.transform.scale(surface, (zone_largeur, zone_hauteur))

    def gerer_evenements(self) -> None:
        """Traite les événements clavier/fenêtre. À appeler à chaque frame."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._quitter = True
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._quitter = True
                elif event.key == pygame.K_SPACE:
                    self.pause = not self.pause

    def actif(self) -> bool:
        return not self._quitter

    def en_pause(self) -> bool:
        return self.pause

    def rendre(self, state: HUDState) -> None:
        """Dessine le HUD complet et rafraîchit l'écran."""
        self.screen.fill(NOIR)

        # 1. Fond : vue caméra (si dispo) ou placeholder.
        zone_cam_x, zone_cam_y = 0, 60
        zone_cam_w = self.largeur - 320
        if self.image_camera_surface is not None:
            self.screen.blit(self.image_camera_surface, (zone_cam_x, zone_cam_y))
        else:
            pygame.draw.rect(self.screen, GRIS_CLAIR,
                             (zone_cam_x, zone_cam_y, zone_cam_w, self.hauteur - 100))
            self._texte(GRIS, "En attente du flux caméra...",
                        (zone_cam_x + zone_cam_w // 2, zone_cam_y + (self.hauteur - 100) // 2),
                        font=self.font_moyen, centrer=True)

        # 2. Bandeau supérieur : niveau + vitesse + temps.
        self._rendre_bandeau_haut(state)

        # 3. Panneau latéral droit : métriques principales.
        self._rendre_panneau_droit(state)

        # 4. Bandeau inférieur : diagnostic ou alerte.
        self._rendre_bandeau_bas(state)

        # 5. Overlay pause.
        if self.pause:
            self._rendre_overlay_pause()

        pygame.display.flip()
        self.clock.tick(60)

    # ------------------------------------------------------------------
    # Détails de rendu
    # ------------------------------------------------------------------

    def _rendre_bandeau_haut(self, state: HUDState) -> None:
        h = 60
        c = COULEURS[state.niveau]
        pygame.draw.rect(self.screen, c["strong"], (0, 0, self.largeur, h))
        # Niveau global (grand, à gauche)
        self._texte(BLANC, state.niveau.name, (24, h // 2), font=self.font_grand, centrer_y=True)
        # Vitesse ego (centrée)
        vitesse_txt = f"{state.vitesse_ego_kmh:5.0f} km/h"
        self._texte(BLANC, vitesse_txt, (self.largeur // 2, h // 2),
                    font=self.font_grand, centrer=True)
        if state.freinage:
            self._texte(BLANC, "▼ FREINAGE",
                        (self.largeur // 2 + 130, h // 2), font=self.font_moyen, centrer_y=True)
        # Temps sim (à droite)
        t_txt = f"t = {state.t:5.1f} s"
        self._texte(BLANC, t_txt, (self.largeur - 24, h // 2),
                    font=self.font_mono, centrer_y=True, aligner_droite=True)

    def _rendre_panneau_droit(self, state: HUDState) -> None:
        x0 = self.largeur - 320
        y0 = 60
        w, h = 320, self.hauteur - 100
        pygame.draw.rect(self.screen, (247, 248, 250), (x0, y0, w, h))
        pygame.draw.line(self.screen, GRIS_CLAIR, (x0, y0), (x0, y0 + h), 2)

        y = y0 + 20
        self._texte(NOIR, "Situation", (x0 + 20, y), font=self.font_titre)
        y += 24
        self._texte(NOIR, f"Agents dans la scène : {state.n_agents}",
                    (x0 + 20, y), font=self.font_petit)
        y += 32

        # Agent le plus critique
        if state.agent_critique:
            ac = state.agent_critique
            self._texte(NOIR, "Agent le plus critique", (x0 + 20, y), font=self.font_titre)
            y += 22
            niv = ac["niveau"]
            c = COULEURS[niv]
            pygame.draw.rect(self.screen, c["bg"], (x0 + 20, y, w - 40, 32))
            pygame.draw.rect(self.screen, c["strong"], (x0 + 20, y, 4, 32))
            self._texte(c["fg"], f"{ac['type']} · {ac['distance']:.0f} m",
                        (x0 + 32, y + 16), font=self.font_moyen, centrer_y=True)
            self._texte(c["fg"], niv.name,
                        (x0 + w - 32, y + 16), font=self.font_moyen,
                        centrer_y=True, aligner_droite=True)
            y += 44

            # Métriques : TTC, THW, DRAC, RSS
            for nom, val, unite in [
                ("TTC", ac.get("ttc"), "s"),
                ("THW", ac.get("thw"), "s"),
                ("DRAC", ac.get("drac"), "m/s²"),
                ("RSS d_min", ac.get("rss"), "m"),
            ]:
                self._rendre_carte_metrique(nom, val, unite, x0 + 20, y, w - 40)
                y += 52
        else:
            self._texte(GRIS, "Aucun agent proche", (x0 + 20, y), font=self.font_petit)

    def _rendre_carte_metrique(self, nom: str, val, unite: str, x: int, y: int, w: int) -> None:
        pygame.draw.rect(self.screen, BLANC, (x, y, w, 44))
        pygame.draw.rect(self.screen, GRIS_CLAIR, (x, y, w, 44), 1)
        self._texte(GRIS, nom, (x + 12, y + 12), font=self.font_titre)
        if val is None:
            txt = "—"
        elif isinstance(val, float):
            txt = f"{val:.2f} {unite}"
        else:
            txt = f"{val} {unite}"
        self._texte(NOIR, txt, (x + w - 12, y + 30), font=self.font_mono,
                    centrer_y=True, aligner_droite=True)

    def _rendre_bandeau_bas(self, state: HUDState) -> None:
        y = self.hauteur - 40
        if state.niveau == RiskLevel.CRITICAL:
            # Alerte critique pulsante (via alpha modulé par le temps)
            import time
            phase = (time.time() * 3.5) % (2 * 3.14159)
            alpha = int(180 + 60 * abs(__import__("math").sin(phase)))
            overlay = pygame.Surface((self.largeur, 40), pygame.SRCALPHA)
            overlay.fill((198, 40, 40, alpha))
            self.screen.blit(overlay, (0, y))
            self._texte(BLANC, f"⚠ CRITICAL — {state.diagnostic}",
                        (self.largeur // 2, y + 20), font=self.font_moyen, centrer=True)
        else:
            pygame.draw.rect(self.screen, (240, 242, 246), (0, y, self.largeur, 40))
            self._texte(GRIS, state.diagnostic, (24, y + 20),
                        font=self.font_petit, centrer_y=True)
            self._texte(GRIS, "ESC : quitter · ESPACE : pause",
                        (self.largeur - 24, y + 20), font=self.font_petit,
                        centrer_y=True, aligner_droite=True)

    def _rendre_overlay_pause(self) -> None:
        overlay = pygame.Surface((self.largeur, self.hauteur), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        self.screen.blit(overlay, (0, 0))
        self._texte(BLANC, "⏸  PAUSE", (self.largeur // 2, self.hauteur // 2),
                    font=self.font_grand, centrer=True)
        self._texte(BLANC, "Appuyer sur ESPACE pour reprendre",
                    (self.largeur // 2, self.hauteur // 2 + 50),
                    font=self.font_moyen, centrer=True)

    # ------------------------------------------------------------------
    # Helper de dessin de texte
    # ------------------------------------------------------------------

    def _texte(self, couleur, txt, pos, font, centrer=False, centrer_y=False, aligner_droite=False):
        surface = font.render(str(txt), True, couleur)
        rect = surface.get_rect()
        if centrer:
            rect.center = pos
        elif centrer_y and aligner_droite:
            rect.midright = pos
        elif centrer_y:
            rect.midleft = pos
        elif aligner_droite:
            rect.topright = pos
        else:
            rect.topleft = pos
        self.screen.blit(surface, rect)

    def fermer(self) -> None:
        pygame.quit()
