"""Mini-carte radar top-down pour la conduite libre.

Affiche une vue à vol d'oiseau centrée sur l'ego avec les acteurs environnants
colorés par niveau. Utile en conduite libre car la caméra ne montre pas ce qui
est sur les côtés — la mini-carte permet de voir un piéton qui s'approche de
la gauche avant qu'il ne soit dans le champ.
"""
from __future__ import annotations

import math
from typing import List

try:
    import pygame  # type: ignore
except ImportError:
    pygame = None  # type: ignore

from risk_engine import RiskLevel
from .palette import BLANC, COULEURS, GRIS, GRIS_CLAIR, NOIR


def dessiner_minimap(surface, x: int, y: int, taille: int,
                     agents_detail: List[dict],
                     rayon_perception_m: float = 60.0,
                     demi_angle_deg: float = 60.0) -> None:
    """Dessine la mini-carte à ``(x, y)`` de côté ``taille`` px.

    L'ego est au centre (triangle bleu pointant vers le haut = « avant »).
    Chaque acteur est un cercle coloré par son niveau de risque, positionné
    proportionnellement à sa distance et son cap relatif.

    Le champ de vision est représenté par un secteur légèrement teinté.
    """
    if pygame is None:
        return

    # Cadre
    pygame.draw.rect(surface, BLANC, (x, y, taille, taille))
    pygame.draw.rect(surface, GRIS_CLAIR, (x, y, taille, taille), 1)

    cx, cy = x + taille // 2, y + taille // 2
    rayon_px = taille // 2 - 6

    # Cône de perception (secteur teinté)
    demi_a_rad = math.radians(demi_angle_deg)
    # Pygame : 0° = 3h, angle croissant sens horaire
    # Notre ego : « avant » = haut. On dessine un secteur de -90-demi_a à -90+demi_a
    points = [(cx, cy)]
    n = 16
    for i in range(n + 1):
        theta = -math.pi / 2 + (-demi_a_rad + 2 * demi_a_rad * i / n)
        px = cx + rayon_px * math.cos(theta)
        py = cy + rayon_px * math.sin(theta)
        points.append((px, py))
    pygame.draw.polygon(surface, (220, 232, 245), points)

    # Cercle de portée
    pygame.draw.circle(surface, GRIS_CLAIR, (cx, cy), rayon_px, 1)

    # Agents : pour chaque agent, convertir (distance_m, cap_relatif) en (px, py)
    for ag in agents_detail:
        d = ag.get("distance", 0.0)
        if d > rayon_perception_m:
            continue
        # cap_relatif_deg est l'orientation de l'acteur par rapport à l'ego, PAS
        # sa position — pour la position on doit reconstruire depuis (x, y).
        # Ici on approxime avec la distance et l'écart latéral si dispo.
        # À défaut, on utilise juste la distance et on met devant.
        frac = d / rayon_perception_m
        px = cx
        py = cy - int(rayon_px * frac)  # devant l'ego
        # On tente une meilleure position si on a les champs dx/dy
        if "dx_relatif" in ag and "dy_relatif" in ag:
            dx = ag["dx_relatif"]
            dy = ag["dy_relatif"]
            # Le repère « écran » : haut = avant ego, droite = droite ego
            # dx (avant) → -y en pixel, dy (droite ego) → +x en pixel
            px = cx + int(rayon_px * dy / rayon_perception_m)
            py = cy - int(rayon_px * dx / rayon_perception_m)

        c = COULEURS[ag["niveau"]]
        pygame.draw.circle(surface, c["strong"], (px, py), 5)

        # --- NOUVEAU : Affichage des métriques sur le radar ---
        font_metriques = pygame.font.SysFont("Courier", 10, bold=True)
        ttc_txt = f"{ag['ttc']:.1f}s" if ag.get("ttc") is not None else "inf"
        drac_txt = f"{ag.get('drac', 0):.1f}"
       
        # On crée l'étiquette (ex: "TTC:2.1s D:4.2")
        label = f"TTC:{ttc_txt} D:{drac_txt}"
        surf_txt = font_metriques.render(label, True, c["strong"])
       
        # On affiche le texte juste à côté du point
        surface.blit(surf_txt, (px + 8, py - 6))
        # ------------------------------------------------------

    # Ego : triangle bleu pointant vers le haut
    pygame.draw.polygon(surface, (37, 99, 235),
                        [(cx, cy - 6), (cx - 5, cy + 5), (cx + 5, cy + 5)])
    pygame.draw.circle(surface, NOIR, (cx, cy), 2)

    # Label
    font = pygame.font.SysFont("Arial", 9, bold=True)
    txt = font.render(f"{rayon_perception_m:.0f} m", True, GRIS)
    surface.blit(txt, (x + 4, y + taille - 14))
