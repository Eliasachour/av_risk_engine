"""
Optimisation des seuils de RiskConfig par descente par coordonnées, sous
contrainte de sécurité.

Fonction de coût ASYMÉTRIQUE : une détection manquée (sous-classement) est une
contrainte DURE — toute configuration qui en produit est rejetée. Parmi les
configurations sûres (zéro détection manquée), on minimise les fausses alarmes.

Méthode : on part du baseline `RiskConfig()` et on règle UN seuil à la fois. Pour
chaque seuil, on balaie des valeurs candidates autour du baseline et on retient
celle qui abaisse le coût — sans jamais créer de détection manquée. On répète
jusqu'à ce que plus aucun réglage n'améliore (convergence).

Lancement : python3 optimize.py
"""
from __future__ import annotations

from dataclasses import replace

from risk_engine import RiskConfig
from calibration import evaluer, format_rapport, synthese

BIG = 1000  # une détection manquée domine toute réduction de fausses alarmes

# Valeurs candidates par seuil, balayées autour du baseline.
# TTC/THW/PET (« haut = plus sûr ») : ABAISSER réduit le sur-classement.
# CI/DRAC (« haut = plus dangereux ») : RELEVER réduit le sur-classement.
# rss_violation_level : niveau attribué à une violation RSS (discret).
CANDIDATES = {
    "ttc_safe":      [2.5, 3.0, 3.5, 4.0, 4.5],
    "ttc_watch":     [1.0, 1.5, 2.0, 2.5],
    "ttc_danger":    [0.5, 0.75, 1.0, 1.25],
    "thw_safe":      [1.0, 1.5, 2.0, 2.5],
    "thw_watch":     [0.5, 0.75, 1.0, 1.5],
    "thw_danger":    [0.3, 0.5, 0.75],
    "pet_safe":      [2.0, 2.5, 3.0, 3.5],
    "pet_watch":     [1.0, 1.5, 2.0],
    "pet_danger":    [0.3, 0.5, 0.75],
    "ci_watch":      [0.3, 0.4, 0.5],
    "ci_danger":     [0.5, 0.6, 0.7],
    "ci_critical":   [0.8, 0.85, 0.9],
    "drac_watch":    [3.0, 4.0, 5.0],
    "drac_danger":   [5.0, 6.0, 7.0],
    "drac_critical": [7.0, 8.0, 9.0],
    # NB : rss_violation_level n'est PAS ici. Le niveau d'une violation RSS est un
    # choix de conception sémantique (« hors de l'enveloppe prouvée sûre »), fixé à
    # DANGER par principe — pas un seuil que l'optimiseur peut relâcher pour gagner
    # sur la calibration. Le modèle RSS reste binaire (respecté / violé).
}


def _config_valide(cfg: RiskConfig) -> bool:
    """Les triplets de seuils doivent rester monotones (bandes cohérentes)."""
    return (
        cfg.ttc_safe > cfg.ttc_watch > cfg.ttc_danger > 0
        and cfg.thw_safe > cfg.thw_watch > cfg.thw_danger > 0
        and cfg.pet_safe > cfg.pet_watch > cfg.pet_danger > 0
        and cfg.ci_watch < cfg.ci_danger < cfg.ci_critical
        and cfg.drac_watch < cfg.drac_danger < cfg.drac_critical
    )


def cout(cfg: RiskConfig) -> float:
    """Coût asymétrique : détections manquées interdites, puis fausses alarmes."""
    s = synthese(evaluer(cfg))
    return BIG * s["sous_classements"] + s["surclassements"]


def optimiser(cfg: RiskConfig = None, passes: int = 5) -> RiskConfig:
    cfg = cfg or RiskConfig()
    meilleur = cout(cfg)
    for _ in range(passes):
        change = False
        for champ, valeurs in CANDIDATES.items():
            for v in valeurs:
                cand = replace(cfg, **{champ: v})
                if not _config_valide(cand):
                    continue
                c = cout(cand)
                if c < meilleur:
                    cfg, meilleur, change = cand, c, True
        if not change:
            break  # convergence : plus aucun réglage n'améliore
    return cfg


def _seuils_modifies(base: RiskConfig, opt: RiskConfig):
    lignes = []
    for champ in CANDIDATES:
        b, o = getattr(base, champ), getattr(opt, champ)
        if b != o:
            lignes.append(f"  {champ:<22} {b} -> {o}")
    return lignes


def _ligne_synthese(cfg: RiskConfig) -> str:
    s = synthese(evaluer(cfg))
    return (f"détections manquées = {s['sous_classements']}   "
            f"fausses alarmes = {s['surclassements']}   "
            f"exactitude = {s['corrects']}/{s['n']} ({100*s['exactitude']:.0f} %)")


if __name__ == "__main__":
    base = RiskConfig()
    opt = optimiser(base)

    print("=== AVANT (baseline RiskConfig) ===")
    print("  " + _ligne_synthese(base))
    print("\n=== APRÈS (seuils optimisés) ===")
    print("  " + _ligne_synthese(opt))

    print("\n=== Seuils modifiés ===")
    mods = _seuils_modifies(base, opt)
    print("\n".join(mods) if mods else "  (aucun réglage n'améliore le baseline)")

    print("\n=== Détail de la calibration optimisée ===")
    print(format_rapport(evaluer(opt)))

    print("\nNote : réglage effectué sur les 24 scénarios de référence. Pour se")
    print("prémunir du surapprentissage, valider ces seuils par validation croisée")
    print("(régler sur un sous-ensemble, vérifier le gain sur le reste) avant adoption.")
