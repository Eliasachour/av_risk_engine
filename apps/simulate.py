"""
Sélectionne les paramètres, lance la simulation, affiche les résultats.

Flux : formulaire (choix des paramètres) -> simulation cinématique -> graphes.

Usage (les options se cumulent) :
    python simulate.py             # formulaire -> simulation -> figures (PNG) ouvertes
    python simulate.py --demo      # scénario de démonstration (sans formulaire)
    python simulate.py --reaction  # l'ego freine selon le risque
    python simulate.py --gif       # enregistre EN PLUS la vue de dessus animée
    python simulate.py --gif --monde  # ... en repère absolu (monde) au lieu du repère ego
    python simulate.py --no-open   # enregistre sans ouvrir les fichiers

Les figures sont toujours enregistrées (metrics.png, comparaison.png) puis
ouvertes avec l'application par défaut du système, ce qui évite la fenêtre
matplotlib interactive (source de crashs « trace trap » sur macOS).
"""

# Ajoute la racine du depot au sys.path pour permettre les imports metier
# (risk_engine, sim, scenarios, calibration, world) meme quand ce script est
# lance directement (`python3 apps/foo.py`). Voir apps/__init__.py.
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import os
import subprocess
import sys

from risk_engine import (
    Agent, ScenarioContext, TypeAgent, assess_risk, format_impact, format_seuils, format_tableau, tableau_metriques,
)
from sim import collision, diagnostic_collision, run


def ouvrir_fichier(chemin: str) -> None:
    """Ouvre un fichier avec l'application par défaut du système d'exploitation."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", chemin], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", chemin], check=False)
        elif os.name == "nt":
            os.startfile(chemin)  # type: ignore[attr-defined]
    except Exception as e:
        print(f"(ouverture automatique impossible : {e} — ouvre {chemin} à la main)")


def scenario_demo() -> ScenarioContext:
    return ScenarioContext(
        vitesse_ego_kmh=80,
        agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=30, distance_m=40, cap_relatif_deg=0)],
    )


def obtenir_scenario():
    """Renvoie (ScenarioContext, ego_freine)."""
    flag = "--reaction" in sys.argv
    if "--demo" in sys.argv:
        return scenario_demo(), flag
    try:
        from scenarios.form import demander_scenario
        res = demander_scenario()
        if res is None:
            return scenario_demo(), flag
        ctx, reaction = res
        return ctx, (reaction or flag)  # la case du formulaire, ou --reaction
    except Exception as e:
        print(f"(formulaire indisponible : {e} — scénario de démonstration utilisé)")
        return scenario_demo(), flag


def table(frames, pas=10):
    print(f"{'t(s)':>5} {'v_ego':>6} {'dist(m)':>8} {'TTC(s)':>7} {'DRAC':>6} {'niveau':>9} {'frein':>6}")
    for f in frames[::pas]:
        d = min((((s.x - f.ego.x) ** 2 + (s.y - f.ego.y) ** 2) ** 0.5) for s in f.agents)
        c = max(f.assessment.details, key=lambda x: x.level) if f.assessment.details else None
        ttc = f"{c.ttc:5.2f}" if c and c.ttc != float("inf") else "  inf"
        drac = f"{c.drac:5.2f}" if c else "    0"
        frein = "oui" if f.ego_accel < 0 else "-"
        print(f"{f.t:5.1f} {f.ego.speed_ms * 3.6:6.0f} {d:8.1f} {ttc:>7} {drac:>6} "
              f"{str(f.assessment.level):>9} {frein:>6}")


def main():
    ctx, reaction = obtenir_scenario()
    if ctx is None:
        print("Saisie annulée.")
        return

    # Table des métriques du scénario saisi (instant initial)
    print("=== Métriques du scénario (TTC, THW, PET, RSS, CI, DRAC) ===")
    table_m = tableau_metriques(ctx)
    print(format_tableau(table_m))
    print()
    print(format_seuils())
    print()
    print(format_impact(table_m))
    eval0 = assess_risk(ctx)
    if eval0.avertissements:
        print("\n[Entrées assainies]")
        for w in eval0.avertissements:
            print("  -", w)
    print()

    frames = run(ctx, reaction=reaction)

    print(f"=== Simulation ({'AVEC' if reaction else 'SANS'} réaction de l'ego) ===")
    table(frames)
    print("collision :", collision(frames))
    if collision(frames):
        print("  ->", diagnostic_collision(frames, ctx))

    try:
        from sim.visualize import animate_topdown, plot_comparaison, plot_metrics
    except ImportError as e:
        print(
            f"\n[Figures non générées] module manquant : {e.name}."
            "\nInstalle les dépendances de visualisation :"
            "\n    pip install matplotlib pillow"
            "\n(La simulation ci-dessus, elle, a bien abouti.)"
        )
        return

    # Les figures sont enregistrées puis ouvertes avec l'app du système
    # (pas de fenêtre matplotlib interactive -> pas de crash sur macOS).
    # Sélection d'agent : --agent N (1-indexé) ; sinon tous les agents.
    agent_index = None
    if "--agent" in sys.argv:
        try:
            agent_index = int(sys.argv[sys.argv.index("--agent") + 1]) - 1
        except (ValueError, IndexError):
            print("(--agent : numéro invalide, affichage de tous les agents)")
    pm = plot_metrics(frames, ctx, "Simulation du risque", reaction=reaction,
                      save_path="metrics.png", agent_index=agent_index)
    pc = plot_comparaison(run(ctx, reaction=False), run(ctx, reaction=True),
                          save_path="comparaison.png")
    print(f"Figures enregistrées : {pm}, {pc}")
    if "--no-open" not in sys.argv:
        ouvrir_fichier(pm)
        ouvrir_fichier(pc)

    # Le GIF est une sortie EN PLUS, déclenchée par --gif.
    # --monde : repère absolu (le piéton traverse perpendiculairement) au lieu du repère ego.
    if "--gif" in sys.argv:
        try:
            pg = animate_topdown(frames, ctx, save_path="topdown.gif",
                                 repere_absolu="--monde" in sys.argv)
            print(f"Animation enregistrée : {pg}")
            if "--no-open" not in sys.argv:
                ouvrir_fichier(pg)
        except Exception as e:
            print(f"[GIF non généré] {e} — vérifie que 'pillow' est installé (pip install pillow).")


if __name__ == "__main__":
    main()
