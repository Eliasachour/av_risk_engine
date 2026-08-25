#!/usr/bin/env python3
"""
Automatisation Grid Search pour AV Risk Engine.
Exécute le benchmark V8 pour chaque combinaison de seuils et consolide les
résumés dans un CSV maître.

Corrections par rapport à la version précédente :
  * Chemins résolus depuis __file__ (indépendants du répertoire courant) : le
    dossier de logs est déduit du script cible, exactement là où V8 l'écrit.
  * stderr capturé et journalisé : si un run plante (ex. RiskConfig n'accepte
    pas un seuil), on le VOIT au lieu de l'avaler.
  * Résumé identifié par diff (nouveaux fichiers), pas par "le plus récent" :
    plus de confusion avec d'anciens résumés qui traînent.
  * sys.executable au lieu de "python" : même interpréteur / venv.
  * Boucle multi-seed optionnelle : un seul run par combinaison n'est pas
    fiable vu le bruit de CARLA.
"""
import os
import sys
import itertools
import subprocess
import time
import csv
import shutil
from pathlib import Path

# --- Configuration du Grid Search ---
SCENARIOS = [3, 4]              # scénarios denses
SEEDS = [42]                   # AJOUTER des graines (ex [42, 123, 7]) pour fiabiliser
TTC_WATCH = [1.5, 2.0, 2.5]
CI_DANGER = [0.5, 0.6, 0.7]
DRAC_DANGER = [5.0, 6.0, 7.0]


DISTANCE_TEST = 330.0
BLOCAGE_MAX_S = 30.0           # court : un run bloqué est un échec, inutile d'attendre 120 s
TIMEOUT_S = 300                # garde-fou temps réel par run

# --- Résolution robuste des chemins (indépendante du CWD) ---
ICI = Path(__file__).resolve().parent
SCRIPT_CIBLE = (ICI / ".." / "apps" / "carla_benchmark_v8_opt.py").resolve()
# V8 écrit ses logs dans <racine>/logs, où racine = parent du dossier du script.
LOGS_V8 = SCRIPT_CIBLE.parent.parent / "logs"
ARCHIVE = LOGS_V8 / "grid_archive"


def _lister_resumes():
    return set(LOGS_V8.glob("*_resume.csv"))


def main():
    if not SCRIPT_CIBLE.exists():
        print(f"X Script cible introuvable : {SCRIPT_CIBLE}")
        print("  Corrige SCRIPT_CIBLE en tête de ce fichier.")
        return 1

    LOGS_V8.mkdir(exist_ok=True)
    ARCHIVE.mkdir(exist_ok=True)

    fichier_maitre = LOGS_V8 / f"master_grid_search_{time.strftime('%Y%m%d_%H%M%S')}.csv"

    combinaisons = list(itertools.product(SCENARIOS, SEEDS, TTC_WATCH, CI_DANGER, DRAC_DANGER))
    total_runs = len(combinaisons)

    print("=" * 60)
    print(f" LANCEMENT DU GRID SEARCH ({total_runs} simulations)")
    print(f"   script  : {SCRIPT_CIBLE}")
    print(f"   logs    : {LOGS_V8}")
    print(f"   maitre  : {fichier_maitre.name}")
    print("=" * 60)

    en_tetes = ["iteration", "scenario", "ttc_watch", "ci_danger", "drac_danger",
                "profil_tm", "seed", "statut_fin", "arrive", "temps_arrivee_s",
                "vitesse_moyenne_kmh", "distance_parcourue_m", "n_collisions",
                "n_freinages", "niveau_max"]
    with open(fichier_maitre, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(en_tetes)

    n_ok = n_echec = n_sans_resume = 0

    for i, (scen, seed, ttc, ci, drac) in enumerate(combinaisons, 1):
        print(f"\n[Run {i}/{total_runs}] Scen:{scen} | seed:{seed} | "
              f"TTC:{ttc}s | CI:{ci} | DRAC:{drac}")

        cmd = [
            "python", SCRIPT_CIBLE,
            "--scenario", str(scen),
            "--direction", "droite",
            "--distance", str(DISTANCE_TEST),
            "--dist-arret", "2.0",
            "--dist-reprise", "3.0",
            "--proximite-critique", "2.0",
            "--blocage-max-s", "120.0",
            "--vitesse", "30.0",
            "--ttc-watch", str(ttc),
            "--ci-danger", str(ci),
            "--drac-danger", str(drac),
            "--no-hud"
        ]

        resumes_avant = _lister_resumes()
        env = os.environ.copy()
        # Défense en profondeur : force Python enfant à utiliser UTF-8 en
        # sortie/erreur, indépendamment de la locale Windows (cp1252).
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            t0 = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=TIMEOUT_S, env=env,
                                    encoding="utf-8", errors="replace")
            dt = time.time() - t0

            if result.returncode == 0:
                print(f" -> code 0 (arrivée) en {dt:.1f}s")
            else:
                print(f" -> code {result.returncode} (bloqué/échec) en {dt:.1f}s")
                # On montre la vraie cause au lieu de l'avaler.
                err = (result.stderr or "").strip()
                if err:
                    tail = "\n".join(err.splitlines()[-6:])
                    print("    stderr (fin) :\n      " + tail.replace("\n", "\n      "))
                    (LOGS_V8 / f"stderr_run{i}.log").write_text(err, encoding="utf-8")

            # Identifier le résumé PRODUIT par ce run (diff, pas "le plus récent").
            # Petite attente : le fichier peut apparaître avec un léger retard
            # après un crash Python (flush disque). On rescanne jusqu'à 2 s.
            nouveaux = _lister_resumes() - resumes_avant
            deadline = time.time() + 2.0
            while not nouveaux and time.time() < deadline:
                time.sleep(0.1)
                nouveaux = _lister_resumes() - resumes_avant

            if nouveaux:
                resume = max(nouveaux, key=os.path.getctime)
                with open(resume, "r", encoding="utf-8") as rf:
                    lignes = list(csv.reader(rf))
                if len(lignes) >= 2:
                    with open(fichier_maitre, "a", newline="", encoding="utf-8") as mf:
                        csv.writer(mf).writerow([i] + lignes[-1])
                    n_ok += 1
                # Archiver plutôt que supprimer (traçabilité)
                shutil.move(str(resume), str(ARCHIVE / resume.name))
            else:
                n_sans_resume += 1
                print("    ! Aucun résumé produit par ce run "
                      "(le benchmark a probablement planté avant l'écriture).")
            if result.returncode != 0:
                n_echec += 1

        except subprocess.TimeoutExpired:
            n_echec += 1
            print(f" -> TIMEOUT (> {TIMEOUT_S}s) : CARLA a probablement freezé. Suivant.")
        except Exception as e:
            n_echec += 1
            print(f" -> ERREUR pilote grid : {e}")

    print("\n" + "=" * 60)
    print(f"GRID SEARCH TERMINÉ — {n_ok} résumés consolidés, "
          f"{n_echec} runs en échec, {n_sans_resume} sans résumé.")
    print(f"Résultats : {fichier_maitre}")
    if n_ok == 0:
        print("\n! Aucun résumé consolidé. Lance d'abord UNE commande à la main")
        print("  (sans --no-hud pour voir) afin d'isoler si le benchmark tourne.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
