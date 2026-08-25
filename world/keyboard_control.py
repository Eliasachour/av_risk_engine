"""
Contrôle clavier pour la conduite libre.

Traduit l'état du clavier (Pygame) en `carla.VehicleControl`, avec un modèle
simple mais suffisant pour une démo :

- **Accélération / freinage** : montent et redescendent progressivement
  (rampe) — évite les à-coups.
- **Direction** : proportionnelle à la durée de maintien, avec un rappel
  vers zéro quand aucune touche latérale n'est pressée.
- **Marche arrière** : bouton dédié (Q ou flèche bas + Shift).

Séparé du HUD : le HUD gère ESC / ESPACE, ce module ne s'occupe que du
véhicule. Deux plans distincts, ça évite les conflits.
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    import pygame  # type: ignore
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False


@dataclass
class EtatClavier:
    """État courant des commandes clavier — persisté entre les ticks."""
    throttle: float = 0.0        # ∈ [0, 1]
    brake: float = 0.0           # ∈ [0, 1]
    steer: float = 0.0           # ∈ [-1, 1]
    reverse: bool = False
    hand_brake: bool = False

    def reset(self):
        self.throttle = 0.0
        self.brake = 0.0
        self.steer = 0.0
        self.reverse = False
        self.hand_brake = False


class ControleClavier:
    """Convertit l'état clavier en `carla.VehicleControl`.

    Les rampes évitent les à-coups (throttle qui saute de 0 à 1 en un tick →
    la voiture s'envole). Les valeurs sont choisies pour donner un pilotage
    « ferme mais civil » à 20 Hz.

    Utilisation à chaque tick :

        keys = pygame.key.get_pressed()
        ctrl = controle.mise_a_jour(keys, dt)
        vehicule_ego.apply_control(ctrl)
    """

    # Vitesses de rampe (par seconde)
    RAMPE_THROTTLE = 2.0      # 0 → 1 en 0.5 s
    RAMPE_BRAKE = 4.0         # 0 → 1 en 0.25 s (freinage plus vif)
    RAMPE_STEER = 3.0         # 0 → 1 en 0.33 s
    RAPPEL_STEER = 5.0        # rappel plus rapide que la mise en butée

    def __init__(self):
        if not _HAS_PYGAME:
            raise RuntimeError("Pygame requis pour le contrôle clavier.")
        self.etat = EtatClavier()

    def mise_a_jour(self, keys, dt: float):
        """Met à jour l'état et renvoie un `carla.VehicleControl` prêt à appliquer.

        Touches supportées :
          - W / ↑     : accélérer
          - S / ↓     : freiner
          - A / ←     : gauche
          - D / →     : droite
          - Q         : marche arrière (bascule)
          - ESPACE    : réservé au HUD (pause) — on l'ignore ici
          - SHIFT     : frein à main
        """
        import carla
        e = self.etat

        # Accélération
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            e.throttle = min(1.0, e.throttle + self.RAMPE_THROTTLE * dt)
        else:
            e.throttle = max(0.0, e.throttle - self.RAMPE_THROTTLE * dt)

        # Frein
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            e.brake = min(1.0, e.brake + self.RAMPE_BRAKE * dt)
        else:
            e.brake = max(0.0, e.brake - self.RAMPE_BRAKE * dt * 2)  # relâche vite

        # Direction avec rappel au centre
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            e.steer = max(-1.0, e.steer - self.RAMPE_STEER * dt)
        elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            e.steer = min(1.0, e.steer + self.RAMPE_STEER * dt)
        else:
            # Rappel vers zéro
            if e.steer > 0:
                e.steer = max(0.0, e.steer - self.RAPPEL_STEER * dt)
            else:
                e.steer = min(0.0, e.steer + self.RAPPEL_STEER * dt)

        # Marche arrière (Q en appui long)
        e.reverse = bool(keys[pygame.K_q])
        # Frein à main (Shift)
        e.hand_brake = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])

        return carla.VehicleControl(
            throttle=e.throttle,
            brake=e.brake,
            steer=e.steer,
            reverse=e.reverse,
            hand_brake=e.hand_brake,
        )

    def freinage_manuel_actif(self) -> bool:
        """Vrai si le conducteur freine activement (utile pour la vigilance)."""
        return self.etat.brake > 0.1 or self.etat.hand_brake
