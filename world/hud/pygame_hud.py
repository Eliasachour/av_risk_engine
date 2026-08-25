"""HUD Pygame : bandeau supérieur, panneaux latéraux, bandeau inférieur.

L'état à afficher est un ``HUDState`` (voir ``state.py``) que le point d'entrée
CARLA reconstruit à chaque tick. Les couleurs et dimensions sont dans
``palette.py``.
"""
from __future__ import annotations

import math
import time
from typing import Optional

try:
    import pygame  # type: ignore
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False

from risk_engine import RiskLevel
from .palette import (
    ACCENT, BLANC, COULEURS, GRIS, GRIS_CLAIR, GRIS_TRES_CLAIR, NOIR, ROUGE_REF,
    H_BANDEAU_TOP, H_BANDEAU_BOT, W_PANNEAU_G, W_PANNEAU_D,
)
from .state import HUDState


class HUD:
    """Fenêtre Pygame + rendu HUD complet.

    Utilisation typique dans le point d'entrée CARLA :

        hud = HUD(largeur=1280, hauteur=720)
        hud.demarrer()
        while hud.actif():
            hud.gerer_evenements()
            if hud.en_pause():
                # ... geler l'ego ...
                continue
            # ... tick CARLA, construction du HUDState ...
            hud.attacher_image_camera(frame_rgb)
            hud.rendre(state)
        hud.fermer()
    """

    def __init__(self, largeur: int = 1280, hauteur: int = 720):
        if not _HAS_PYGAME:
            raise RuntimeError("Pygame n'est pas installe. `pip install pygame numpy`.")
        self.largeur = largeur
        self.hauteur = hauteur
        self.screen = None
        self.clock = None
        self.image_camera_surface = None
        self.pause = False
        self.aide_visible = False
        # Cadence de la boucle de rendu. En mode synchrone CARLA, le monde
        # avance de `fixed_delta_seconds` par tick : si la boucle tourne plus
        # vite que 1/dt, le temps simule defile plus vite que le temps reel et
        # la conduite devient injouable. `cadence_hz` doit donc valoir le tick
        # rate de la simulation.
        self.cadence_hz = 60
        self._quitter = False
        self._evenements_bruts = []   # relayés à l'appelant (météo, etc.)

    def demarrer(self) -> None:
        """Ouvre la fenêtre et initialise les polices.

        Si la fenêtre existe déjà (cas du menu de configuration qui a ouvert
        l'affichage avant nous), utiliser `attacher(screen)` plutôt que cette
        méthode : elle éviterait un second `set_mode` inutile.
        """
        pygame.init()
        pygame.display.set_caption("AV Risk Engine - CARLA HUD")
        self.screen = pygame.display.set_mode((self.largeur, self.hauteur))
        self.clock = pygame.time.Clock()
        self._init_polices()

    def attacher(self, screen) -> None:
        """Réutilise une fenêtre Pygame déjà ouverte (menu -> HUD sans coupure)."""
        self.screen = screen
        self.largeur, self.hauteur = screen.get_size()
        self.clock = pygame.time.Clock()
        self._init_polices()

    def _init_polices(self) -> None:
        # Polices : Arial (safe list) + Courier pour les valeurs numeriques
        self.font_titre = pygame.font.SysFont("Arial", 11, bold=True)
        self.font_micro = pygame.font.SysFont("Arial", 10)
        self.font_petit = pygame.font.SysFont("Arial", 12)
        self.font_moyen = pygame.font.SysFont("Arial", 16, bold=True)
        self.font_grand = pygame.font.SysFont("Arial", 32, bold=True)
        self.font_hero = pygame.font.SysFont("Arial", 40, bold=True)
        self.font_mono = pygame.font.SysFont("Courier", 13, bold=True)

    def attacher_image_camera(self, image_rgb) -> None:
        """Attache la derniere image camera (numpy array HxWx3 RGB)."""
        if image_rgb is None:
            return
        surface = pygame.image.frombuffer(image_rgb.tobytes(), image_rgb.shape[1::-1], "RGB")
        w = self.largeur - W_PANNEAU_G - W_PANNEAU_D
        h = self.hauteur - H_BANDEAU_TOP - H_BANDEAU_BOT
        self.image_camera_surface = pygame.transform.scale(surface, (w, h))

    def gerer_evenements(self) -> None:
        """Traite les événements du HUD et mémorise les autres.

        Les touches que le HUD ne gère pas (météo, etc.) sont conservées dans
        `_evenements_bruts` : l'appelant les récupère via `evenements()` et les
        transmet à qui de droit. Sans ce relais, `pygame.event.get()` viderait
        la file et le contrôle météo ne recevrait jamais rien.
        """
        self._evenements_bruts = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._quitter = True
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._quitter = True
                    continue
                if event.key == pygame.K_SPACE:
                    self.pause = not self.pause
                    continue
                if event.key == pygame.K_h:
                    self.aide_visible = not self.aide_visible
                    continue
            self._evenements_bruts.append(event)

    def evenements(self):
        """Événements non consommés par le HUD (à passer au contrôle météo)."""
        return self._evenements_bruts

    def actif(self) -> bool:
        return not self._quitter

    def en_pause(self) -> bool:
        return self.pause

    def rendre(self, state: HUDState) -> None:
        """Dessine le HUD complet et rafraichit l'ecran."""
        self.screen.fill(NOIR)
        self._rendre_zone_camera()
        self._rendre_bandeau_haut(state)
        self._rendre_panneau_gauche(state)
        self._rendre_panneau_droit(state)
        # En conduite libre, ajouter la mini-carte au-dessus du panneau agents

        self._rendre_minimap(state)
        self._rendre_badge_assistance(state)
        if state.alerte_msg:
            self._rendre_bandeau_alerte(state)
            
        self._rendre_bandeau_bas(state)
        if state.reco_message:
            self._rendre_recommandation(state)
        if self.aide_visible:
            self._rendre_overlay_aide()
        if self.pause:
            self._rendre_overlay_pause()
        pygame.display.flip()
        self.clock.tick(self.cadence_hz)

    def _rendre_minimap(self, state: HUDState) -> None:
        """Mini-carte radar dans le panneau gauche."""
        from .minimap import dessiner_minimap
        taille = W_PANNEAU_G - 20
        x, y = 10, self.hauteur - H_BANDEAU_BOT - taille - 44
        dessiner_minimap(
            self.screen, x, y, taille,
            state.agents_detail,
            rayon_perception_m=state.rayon_perception_m,
            demi_angle_deg=state.demi_angle_perception_deg,
        )

    def _rendre_badge_assistance(self, state: HUDState) -> None:
        """Badge en bas à droite : mode d'assistance (EVAL / ALERTE / AEB)."""
        w, h = 90, 26
        x = self.largeur - W_PANNEAU_D + 14
        # 44 px de garde : le bandeau d'alerte flotte juste au-dessus du
        # bandeau bas et masquerait le badge sinon.
        y = self.hauteur - H_BANDEAU_BOT - h - 44

        # Couleur : gris pour EVAL, orange pour ALERTE, rouge pour AEB
        couleur = {
            "EVAL": (90, 100, 120),
            "ALERTE": (239, 108, 0),
            "AEB": (198, 40, 40),
        }.get(state.assistance, GRIS)
        pygame.draw.rect(self.screen, couleur, (x, y, w, h), border_radius=4)
        self._texte(BLANC, state.assistance, (x + w // 2, y + h // 2),
                    font=self.font_titre, centrer=True)

        # Badge « ORACLE » à côté (transparence sur la source de perception)
        self._texte(GRIS, "perception : oracle",
                    (x + w + 10, y + h // 2),
                    font=self.font_micro, centrer_y=True)

    def _rendre_bandeau_alerte(self, state: HUDState) -> None:
        """Bandeau alerte flottant au-dessus du bandeau bas."""
        import time as _time
        y = self.hauteur - H_BANDEAU_BOT - 34
        phase = (_time.time() * 3.0) % (2 * math.pi)
        alpha = int(200 + 55 * abs(math.sin(phase)))
        # Rouge si critique, orange sinon
        base_col = (198, 40, 40) if state.aeb_engage else (239, 108, 0)
        overlay = pygame.Surface((self.largeur, 30), pygame.SRCALPHA)
        overlay.fill((*base_col, alpha))
        self.screen.blit(overlay, (0, y))
        self._texte(BLANC, state.alerte_msg,
                    (self.largeur // 2, y + 15),
                    font=self.font_moyen, centrer=True)

    # ------------------------------------------------------------------
    # Sous-rendus
    # ------------------------------------------------------------------

    def _rendre_zone_camera(self) -> None:
        x, y = W_PANNEAU_G, H_BANDEAU_TOP
        w = self.largeur - W_PANNEAU_G - W_PANNEAU_D
        h = self.hauteur - H_BANDEAU_TOP - H_BANDEAU_BOT
        if self.image_camera_surface is not None:
            self.screen.blit(self.image_camera_surface, (x, y))
        else:
            pygame.draw.rect(self.screen, GRIS_CLAIR, (x, y, w, h))
            self._texte(GRIS, "En attente du flux camera...",
                        (x + w // 2, y + h // 2), font=self.font_moyen, centrer=True)

    def _rendre_bandeau_haut(self, state: HUDState) -> None:
        h = H_BANDEAU_TOP
        c = COULEURS[state.niveau]
        pygame.draw.rect(self.screen, c["strong"], (0, 0, self.largeur, h))
        self._texte(BLANC, state.niveau.name, (18, h // 2),
                    font=self.font_hero, centrer_y=True)
        self._texte(BLANC, f"{state.vitesse_ego_kmh:5.0f} km/h",
                    (self.largeur // 2, h // 2 - 8), font=self.font_grand, centrer=True)
        # Sous la vitesse : limite reelle du troncon (lue dans la carte CARLA)
        sous = f"limite {state.limite_vitesse_kmh}" if state.limite_vitesse_kmh else \
               f"cible {state.v_cible_kmh:.0f}"
        exces = (state.limite_vitesse_kmh
                 and state.vitesse_ego_kmh > state.limite_vitesse_kmh + 5)
        self._texte((255, 225, 120) if exces else BLANC, sous,
                    (self.largeur // 2, h // 2 + 18), font=self.font_petit, centrer=True)
        # Pastilles de contexte routier, a gauche de la vitesse
        px = 215   # juste apres le nom du niveau, sans chevaucher la vitesse
        pastilles = []
        if state.feu and state.feu != "aucun":
            coul = {"rouge": (198, 40, 40), "jaune": (249, 168, 37),
                    "vert": (46, 125, 50)}.get(state.feu, GRIS)
            pastilles.append((f"FEU {state.feu.upper()}", coul))
        if state.geometrie == "virage":
            pastilles.append(("VIRAGE", (120, 90, 160)))
        if state.hors_voie:
            pastilles.append(("HORS VOIE", (198, 40, 40)))
        if state.obstacle_statique_m is not None:
            pastilles.append((f"OBSTACLE {state.obstacle_statique_m:.0f}m", (198, 40, 40)))
        if state.n_collisions:
            coul = (198, 40, 40) if state.collision_recente else (120, 60, 60)
            pastilles.append((f"CHOCS {state.n_collisions}", coul))
        for texte, coul in pastilles[:3]:
            surf = self.font_titre.render(texte, True, BLANC)
            larg = surf.get_width() + 14
            pygame.draw.rect(self.screen, coul, (px, h // 2 - 9, larg, 18))
            self.screen.blit(surf, (px + 7, h // 2 - 7))
            px += larg + 6

        badge_x = self.largeur // 2 + 120
        libelles = {
            "manuel": "MANUEL", "pause": "PAUSE", "nominal": "NOMINAL",
            "proportionnel": "PROPORT.", "physique": "PHYSIQUE", "off": "PASSIF",
        }
        self._texte(BLANC, libelles.get(state.mode_ctrl, state.mode_ctrl.upper()),
                    (badge_x + 50, h // 2), font=self.font_moyen, centrer=True)
        if state.freinage:
            self._texte(BLANC, "FREIN", (badge_x + 130, h // 2),
                        font=self.font_moyen, centrer_y=True)
        self._texte(BLANC, f"t = {state.t:5.1f} s",
                    (self.largeur - 18, h // 2 - 9), font=self.font_mono,
                    centrer_y=True, aligner_droite=True)
        # Facteur temps reel : 1.0 = la simulation suit l'horloge. Au-dela,
        # elle est en avance (conduite trop rapide) ; en dessous, elle rame.
        if state.facteur_temps_reel:
            couleur = BLANC if 0.85 <= state.facteur_temps_reel <= 1.15 else (255, 235, 160)
            self._texte(couleur, f"x{state.facteur_temps_reel:.2f}  {state.fps:.0f} fps",
                        (self.largeur - 18, h // 2 + 11), font=self.font_micro,
                        centrer_y=True, aligner_droite=True)

    def _rendre_panneau_gauche(self, state: HUDState) -> None:
        """Panneau agents : liste triee par criticite, max 5."""
        x0, y0 = 0, H_BANDEAU_TOP
        w = W_PANNEAU_G
        h = self.hauteur - H_BANDEAU_TOP - H_BANDEAU_BOT
        pygame.draw.rect(self.screen, GRIS_TRES_CLAIR, (x0, y0, w, h))
        pygame.draw.line(self.screen, GRIS_CLAIR, (x0 + w, y0), (x0 + w, y0 + h), 2)

        y = y0 + 12
        self._texte(GRIS, f"AGENTS DETECTES  {state.n_agents}",
                    (x0 + 14, y), font=self.font_titre)
        y += 22

        ordre_niv = {"CRITICAL": 3, "DANGER": 2, "WATCH": 1, "SAFE": 0}
        agents_tries = sorted(
            state.agents_detail,
            key=lambda a: (
                -ordre_niv.get(a["niveau"].name, 0),
                a["ttc"] if a["ttc"] is not None else 1e9,
            ),
        )[:5]

        for ag in agents_tries:
            c = COULEURS[ag["niveau"]]
            pygame.draw.rect(self.screen, BLANC, (x0 + 10, y, w - 20, 62))
            pygame.draw.rect(self.screen, c["strong"], (x0 + 10, y, 4, 62))
            self._texte(NOIR, ag["type"], (x0 + 20, y + 12), font=self.font_moyen)
            self._texte(c["fg"], ag["niveau"].name,
                        (x0 + w - 20, y + 12), font=self.font_titre, aligner_droite=True)
            self._texte(GRIS, f"{ag['distance']:.0f} m",
                        (x0 + w - 20, y + 30), font=self.font_petit, aligner_droite=True)
            ttc_s = f"{ag['ttc']:.1f}s" if ag["ttc"] is not None else "inf"
            self._texte(GRIS, f"TTC {ttc_s}   DRAC {ag['drac']:.1f}",
                        (x0 + 20, y + 44), font=self.font_micro)
            y += 68

        if not agents_tries:
            self._texte(GRIS, "Aucun agent detecte",
                        (x0 + 14, y + 20), font=self.font_petit)

    def _rendre_panneau_droit(self, state: HUDState) -> None:
        """Panneau jauges physiques pour l'agent le plus critique."""
        x0 = self.largeur - W_PANNEAU_D
        y0 = H_BANDEAU_TOP
        w = W_PANNEAU_D
        h = self.hauteur - H_BANDEAU_TOP - H_BANDEAU_BOT
        pygame.draw.rect(self.screen, GRIS_TRES_CLAIR, (x0, y0, w, h))
        pygame.draw.line(self.screen, GRIS_CLAIR, (x0, y0), (x0, y0 + h), 2)

        y = y0 + 12
        self._texte(GRIS, "JAUGES PHYSIQUES", (x0 + 14, y), font=self.font_titre)
        y += 22

        ac = state.agent_critique
        if ac is None:
            self._texte(GRIS, "En attente d'un agent proche",
                        (x0 + 14, y + 12), font=self.font_petit)
            return

        c = COULEURS[ac["niveau"]]
        self._texte(NOIR, f"{ac['type']} a {ac['distance']:.0f} m",
                    (x0 + 14, y), font=self.font_moyen)
        y += 22
        self._texte(c["fg"], ac["niveau"].name, (x0 + 14, y), font=self.font_titre)
        y += 18

        # --- Les six métriques du moteur, en clair ---
        m = state.metriques or {}
        self._texte(GRIS, "METRIQUES", (x0 + 14, y), font=self.font_titre)
        y += 18
        for nom in ("TTC", "THW", "PET", "RSS", "CI", "DRAC"):
            if nom not in m:
                continue
            valeur, unite, niveau = m[nom]
            c = COULEURS[niveau]
            decisive = (nom == state.metrique_decisive)
            # Fond coloré selon le niveau de cette métrique
            pygame.draw.rect(self.screen, c["bg"], (x0 + 14, y, w - 28, 20))
            pygame.draw.rect(self.screen, c["strong"], (x0 + 14, y, 3, 20))
            libelle = f"> {nom}" if decisive else f"  {nom}"
            self._texte(c["fg"], libelle, (x0 + 22, y + 3),
                        font=self.font_mono if decisive else self.font_petit)
            txt = "inf" if valeur is None else f"{valeur:.2f} {unite}"
            self._texte(c["fg"], txt, (x0 + w - 22, y + 3),
                        font=self.font_mono, aligner_droite=True)
            y += 22

        y += 6
        # --- Grandeurs dérivées ---
        for libelle, val, fmt in (
            ("TTC effectif", state.ttc_effectif, "{:.2f} s"),
            ("Marge contexte", state.marge_contextuelle, "x{:.2f}"),
            ("d / d_RSS", state.ratio_rss, "{:.2f}"),
            ("Metriques concordantes", state.corroboration, "{:.0f} / 6"),
        ):
            if val is None:
                continue
            self._texte(GRIS, libelle, (x0 + 22, y), font=self.font_micro)
            self._texte(NOIR, fmt.format(val), (x0 + w - 22, y),
                        font=self.font_micro, aligner_droite=True)
            y += 15

        y += 8
        # --- Jauges physiques (position dans les seuils) ---
        jauges = [
            {"nom": "TTC", "val": ac["ttc"], "max": 6.0, "seuils": [1, 2, 4],
             "unite": "s", "hi_safe": True},
            {"nom": "DRAC vs mu.g", "val": ac["drac"], "max": state.mu_g or 8.8,
             "seuils": None, "unite": "m/s2", "hi_safe": False,
             "ref_line": state.mu_g},
        ]
        for jauge in jauges:
            self._rendre_jauge(x0 + 14, y, w - 28, 46, jauge)
            y += 54

    def _rendre_jauge(self, x, y, w, h, jauge):
        val = jauge["val"]
        vmax = jauge["max"]
        pygame.draw.rect(self.screen, BLANC, (x, y, w, h))

        # Bandes de seuils (TTC/THW : haut = safe = vert a droite)
        if jauge["seuils"] and jauge["hi_safe"]:
            s = jauge["seuils"]
            bandes = [
                (0,            s[0] / vmax, (255, 205, 210)),
                (s[0] / vmax,  s[1] / vmax, (255, 224, 178)),
                (s[1] / vmax,  s[2] / vmax, (255, 248, 225)),
                (s[2] / vmax,  1.0,          (230, 244, 234)),
            ]
            for x1, x2, col in bandes:
                pygame.draw.rect(self.screen, col,
                                 (x + int(x1 * w), y + h - 18, int((x2 - x1) * w), 12))
        else:
            pygame.draw.rect(self.screen, GRIS_TRES_CLAIR, (x, y + h - 18, w, 12))

        # Curseur bleu
        if val is not None and math.isfinite(val):
            frac = max(0.0, min(1.0, val / vmax))
            cx = x + int(frac * w)
            pygame.draw.polygon(self.screen, ACCENT,
                                [(cx, y + h - 25), (cx - 5, y + h - 20), (cx + 5, y + h - 20)])
            pygame.draw.rect(self.screen, ACCENT, (cx - 1, y + h - 20, 2, 14))

        # Ligne de reference (mu*g, vitesse cible)
        if jauge.get("ref_line") is not None and jauge["ref_line"] > 0:
            rx = x + int((jauge["ref_line"] / vmax) * w)
            pygame.draw.line(self.screen, ROUGE_REF,
                             (rx, y + h - 26), (rx, y + h - 4), 2)

        # Labels
        self._texte(NOIR, jauge["nom"], (x, y + 2), font=self.font_titre)
        val_txt = "inf" if val is None else f"{val:.1f} {jauge['unite']}"
        self._texte(NOIR, val_txt, (x + w, y + 2),
                    font=self.font_mono, aligner_droite=True)

    def _rendre_bandeau_bas(self, state: HUDState) -> None:
        y = self.hauteur - H_BANDEAU_BOT
        if state.niveau == RiskLevel.CRITICAL:
            phase = (time.time() * 3.5) % (2 * math.pi)
            alpha = int(180 + 60 * abs(math.sin(phase)))
            overlay = pygame.Surface((self.largeur, H_BANDEAU_BOT), pygame.SRCALPHA)
            overlay.fill((198, 40, 40, alpha))
            self.screen.blit(overlay, (0, y))
            self._texte(BLANC, f"CRITICAL - {state.diagnostic}",
                        (self.largeur // 2, y + H_BANDEAU_BOT // 2),
                        font=self.font_moyen, centrer=True)
        else:
            pygame.draw.rect(self.screen, (240, 242, 246),
                             (0, y, self.largeur, H_BANDEAU_BOT))
            gauche = state.diagnostic
            if state.meteo_resume:
                gauche = f"{state.meteo_resume}   |   {gauche}"
            self._texte(GRIS, gauche,
                        (18, y + H_BANDEAU_BOT // 2), font=self.font_petit, centrer_y=True)
            self._texte(GRIS, "H : aide   ESPACE : pause   ESC : quitter",
                        (self.largeur - 18, y + H_BANDEAU_BOT // 2),
                        font=self.font_petit, centrer_y=True, aligner_droite=True)

    def _rendre_recommandation(self, state: HUDState) -> None:
        """Bandeau de consigne, sous la zone caméra.

        C'est la sortie destinée à l'apprentissage : une action chiffrée et sa
        justification physique, plutôt qu'un simple voyant coloré. Un conducteur
        novice peut agir sur « ralentir de 15 km/h » ; il ne peut rien faire
        d'un carré rouge.
        """
        couleurs = {
            0: ((232, 245, 235), (27, 94, 32)),      # aucune action
            1: ((255, 248, 225), (109, 82, 0)),      # anticiper
            2: ((255, 224, 178), (122, 61, 0)),      # agir
            3: ((198, 40, 40), BLANC),               # urgent
        }
        fond, texte = couleurs.get(state.reco_urgence, couleurs[0])

        h_bandeau = 52
        x = W_PANNEAU_G
        largeur = self.largeur - W_PANNEAU_G - W_PANNEAU_D
        y = self.hauteur - H_BANDEAU_BOT - h_bandeau

        pygame.draw.rect(self.screen, fond, (x, y, largeur, h_bandeau))
        pygame.draw.rect(self.screen, texte, (x, y, 4, h_bandeau))

        self._texte(texte, state.reco_message, (x + 18, y + 9),
                    font=self.font_moyen)
        if state.reco_justification:
            self._texte(texte, state.reco_justification, (x + 18, y + 31),
                        font=self.font_petit)

    def _rendre_overlay_aide(self):
        """Panneau d'aide clavier, basculé par la touche H."""
        lignes = [
            ("CONDUITE", ""),
            ("W / fleche haut", "accelerer"),
            ("S / fleche bas", "freiner"),
            ("A / D", "gauche / droite"),
            ("Q", "marche arriere (maintenir)"),
            ("SHIFT", "frein a main"),
            ("", ""),
            ("METEO - PRESETS", ""),
            ("F1", "clair"),
            ("F2", "couvert"),
            ("F3", "pluie"),
            ("F4", "orage"),
            ("F5", "brouillard"),
            ("F6", "neige / verglas"),
            ("F7", "nuit claire"),
            ("", ""),
            ("METEO - REGLAGES FINS", ""),
            ("I / K", "nuages + / -"),
            ("O / L", "pluie + / -"),
            ("P / M", "brouillard + / -"),
            ("N / B", "soleil plus haut / plus bas"),
            ("", ""),
            ("GENERAL", ""),
            ("H", "afficher / masquer cette aide"),
            ("ESPACE", "pause"),
            ("ESC", "quitter"),
        ]
        w, h = 460, 22 * len(lignes) + 56
        x = (self.largeur - w) // 2
        y = (self.hauteur - h) // 2

        overlay = pygame.Surface((self.largeur, self.hauteur), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        pygame.draw.rect(self.screen, BLANC, (x, y, w, h))
        pygame.draw.rect(self.screen, ACCENT, (x, y, w, 4))
        self._texte(NOIR, "Commandes", (x + 22, y + 18), font=self.font_moyen)

        yy = y + 46
        for touche, desc in lignes:
            if touche and not desc:
                self._texte(ACCENT, touche, (x + 22, yy), font=self.font_titre)
            elif touche:
                self._texte(NOIR, touche, (x + 34, yy), font=self.font_mono)
                self._texte(GRIS, desc, (x + 200, yy), font=self.font_petit)
            yy += 22

    def _rendre_overlay_pause(self):
        overlay = pygame.Surface((self.largeur, self.hauteur), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        self.screen.blit(overlay, (0, 0))
        self._texte(BLANC, "PAUSE", (self.largeur // 2, self.hauteur // 2),
                    font=self.font_hero, centrer=True)
        self._texte(BLANC, "Appuyer sur ESPACE pour reprendre",
                    (self.largeur // 2, self.hauteur // 2 + 40),
                    font=self.font_moyen, centrer=True)

    # ------------------------------------------------------------------
    def _texte(self, couleur, txt, pos, font,
               centrer=False, centrer_y=False, aligner_droite=False):
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

    def fermer(self):
        pygame.quit()
