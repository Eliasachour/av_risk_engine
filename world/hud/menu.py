"""
Menu de configuration Pygame — remplace le formulaire tkinter.

Tout se passe dans la même fenêtre que le HUD : plus de fenêtre séparée qui
s'ouvre puis se ferme. L'utilisateur navigue au clavier, ajuste les valeurs,
et lance la simulation sans quitter l'écran.

Commandes :
    HAUT / BAS      changer de ligne
    GAUCHE / DROITE changer la valeur
    ENTRÉE          lancer la simulation
    ÉCHAP           annuler

Le menu réutilise la même palette que le HUD (world/hud/palette.py) pour que
l'ensemble forme une interface cohérente.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence

try:
    import pygame  # type: ignore
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False

from .palette import (
    ACCENT, BLANC, GRIS, GRIS_CLAIR, GRIS_TRES_CLAIR, NOIR, ROUGE_REF,
)


# ---------------------------------------------------------------------------
# Description d'un réglage
# ---------------------------------------------------------------------------


@dataclass
class Reglage:
    """Une ligne du menu : un libellé, des valeurs possibles, un index courant."""
    cle: str                       # nom du champ dans CarlaConfig
    libelle: str
    valeurs: Sequence[Any]         # liste de choix possibles
    index: int = 0
    aide: str = ""                 # ligne d'explication affichée en bas
    format: Optional[Callable[[Any], str]] = None

    @property
    def valeur(self) -> Any:
        return self.valeurs[self.index]

    def texte_valeur(self) -> str:
        if self.format:
            return self.format(self.valeur)
        v = self.valeur
        if isinstance(v, bool):
            return "oui" if v else "non"
        return str(v)

    def suivant(self) -> None:
        self.index = (self.index + 1) % len(self.valeurs)

    def precedent(self) -> None:
        self.index = (self.index - 1) % len(self.valeurs)

    def caler_sur(self, valeur: Any) -> None:
        """Positionne l'index sur `valeur` si elle est dans la liste."""
        try:
            self.index = list(self.valeurs).index(valeur)
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Le menu
# ---------------------------------------------------------------------------


class MenuConfig:
    """Menu plein écran rendu dans la fenêtre Pygame déjà ouverte.

    Utilisation :

        pygame.init()
        screen = pygame.display.set_mode((1280, 720))
        menu = MenuConfig(screen, reglages, titre="Conduite libre")
        if menu.boucle():          # bloquant jusqu'à ENTRÉE ou ÉCHAP
            valeurs = menu.valeurs()   # dict {cle: valeur}
        else:
            ...   # annulé
    """

    def __init__(self, screen, reglages: List[Reglage],
                 titre: str = "Configuration",
                 sous_titre: str = ""):
        if not _HAS_PYGAME:
            raise RuntimeError("Pygame requis pour le menu de configuration.")
        self.screen = screen
        self.reglages = reglages
        self.titre = titre
        self.sous_titre = sous_titre
        self.curseur = 0
        self.largeur, self.hauteur = screen.get_size()
        self.clock = pygame.time.Clock()

        self.f_titre = pygame.font.SysFont("Arial", 34, bold=True)
        self.f_sous = pygame.font.SysFont("Arial", 15)
        self.f_label = pygame.font.SysFont("Arial", 17)
        self.f_valeur = pygame.font.SysFont("Courier New", 17, bold=True)
        self.f_aide = pygame.font.SysFont("Arial", 13, italic=True)
        self.f_pied = pygame.font.SysFont("Arial", 13)

    # ------------------------------------------------------------------

    def boucle(self) -> bool:
        """Boucle bloquante. Renvoie True si lancé, False si annulé."""
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                if event.type != pygame.KEYDOWN:
                    continue
                k = event.key
                if k == pygame.K_ESCAPE:
                    return False
                if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return True
                if k in (pygame.K_DOWN, pygame.K_s):
                    self.curseur = (self.curseur + 1) % len(self.reglages)
                elif k in (pygame.K_UP, pygame.K_w):
                    self.curseur = (self.curseur - 1) % len(self.reglages)
                elif k in (pygame.K_RIGHT, pygame.K_d):
                    self.reglages[self.curseur].suivant()
                elif k in (pygame.K_LEFT, pygame.K_a):
                    self.reglages[self.curseur].precedent()

            self._rendre()
            self.clock.tick(60)

    def valeurs(self) -> dict:
        return {r.cle: r.valeur for r in self.reglages}

    # ------------------------------------------------------------------

    def _rendre(self) -> None:
        self.screen.fill(NOIR)

        # Panneau central
        marge_x = 90
        pan_w = self.largeur - 2 * marge_x
        pan_y = 70
        pan_h = self.hauteur - 150
        pygame.draw.rect(self.screen, GRIS_TRES_CLAIR,
                         (marge_x, pan_y, pan_w, pan_h))
        pygame.draw.rect(self.screen, ACCENT, (marge_x, pan_y, pan_w, 4))

        # Titre
        self._txt(NOIR, self.titre, (marge_x + 26, pan_y + 26), self.f_titre)
        if self.sous_titre:
            self._txt(GRIS, self.sous_titre, (marge_x + 26, pan_y + 68), self.f_sous)

        # Lignes de réglage
        y = pan_y + 105
        pas = 34
        for i, r in enumerate(self.reglages):
            actif = (i == self.curseur)
            if actif:
                pygame.draw.rect(self.screen, (225, 235, 250),
                                 (marge_x + 14, y - 5, pan_w - 28, pas - 3))
                pygame.draw.rect(self.screen, ACCENT,
                                 (marge_x + 14, y - 5, 3, pas - 3))

            couleur_label = NOIR if actif else GRIS
            self._txt(couleur_label, r.libelle, (marge_x + 30, y), self.f_label)

            # Valeur, avec chevrons quand la ligne est active
            txt_val = r.texte_valeur()
            x_val = marge_x + pan_w - 40
            if actif:
                self._txt(ACCENT, ">", (x_val + 12, y), self.f_valeur)
                surf = self.f_valeur.render(txt_val, True, ACCENT)
                self.screen.blit(surf, (x_val - surf.get_width() - 4, y))
                self._txt(ACCENT, "<",
                          (x_val - surf.get_width() - 30, y), self.f_valeur)
            else:
                surf = self.f_valeur.render(txt_val, True, NOIR)
                self.screen.blit(surf, (x_val - surf.get_width(), y))
            y += pas

        # Ligne d'aide du réglage courant
        aide = self.reglages[self.curseur].aide
        if aide:
            self._txt(GRIS, aide, (marge_x + 30, pan_y + pan_h - 46), self.f_aide)

        # Pied de page : commandes
        pygame.draw.rect(self.screen, (240, 242, 246),
                         (0, self.hauteur - 42, self.largeur, 42))
        self._txt(GRIS,
                  "HAUT/BAS : ligne     GAUCHE/DROITE : valeur     "
                  "ENTREE : lancer     ECHAP : quitter",
                  (marge_x, self.hauteur - 30), self.f_pied)

        pygame.display.flip()

    def _txt(self, couleur, texte, pos, font):
        self.screen.blit(font.render(str(texte), True, couleur), pos)
