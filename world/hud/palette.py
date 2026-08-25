"""Palette et constantes visuelles du HUD.

Les couleurs par niveau de risque sont volontairement alignées avec celles de
l'interface web (thème clair) : cohérence visuelle entre les deux surfaces, et
un seul endroit à toucher si on veut changer la charte.
"""
from __future__ import annotations

from risk_engine import RiskLevel


# --- Couleurs par niveau de risque (miroir de l'interface web) ---
COULEURS = {
    RiskLevel.SAFE:     {"bg": (230, 244, 234), "fg": (27, 94, 32),  "strong": (46, 125, 50)},
    RiskLevel.WATCH:    {"bg": (255, 248, 225), "fg": (109, 82, 0),  "strong": (249, 168, 37)},
    RiskLevel.DANGER:   {"bg": (255, 224, 178), "fg": (122, 61, 0),  "strong": (239, 108, 0)},
    RiskLevel.CRITICAL: {"bg": (255, 205, 210), "fg": (138, 28, 28), "strong": (198, 40, 40)},
}

# --- Couleurs neutres ---
BLANC = (255, 255, 255)
NOIR = (26, 31, 46)
GRIS = (90, 100, 120)
GRIS_CLAIR = (228, 232, 238)
GRIS_TRES_CLAIR = (247, 248, 250)
ACCENT = (37, 99, 235)          # bleu ACC (curseur des jauges)
ROUGE_REF = (198, 40, 40)       # lignes de référence (µ·g, vitesse cible)

# --- Dimensions du HUD ---
H_BANDEAU_TOP = 60
H_BANDEAU_BOT = 40
W_PANNEAU_G = 260
W_PANNEAU_D = 280
