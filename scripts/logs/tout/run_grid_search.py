#!/usr/bin/env python3
"""
Automatisation Grid Search pour AV Risk Engine
Exécute le benchmark V8 pour toutes les combinaisons de seuils et consolide les résultats.
"""
import os
import itertools
import subprocess
import time
import csv
from pathlib import Path

# --- Configuration du Grid Search ---
SCENARIOS = [2, 4]  # On cible directement les scénarios les plus denses
TTC_WATCH = [1.5, 2.0, 2.5]
CI_DANGER = [0.5, 0.6, 0.7]
DRAC_DANGER = [5.0, 6.0, 7.0]

DISTANCE_TEST = 400.0
SCRIPT_CIBLE = "../apps/carla_benchmark_v8_opt.py"

def main():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    fichier_maitre = log_dir / f"master_grid_search_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    
    combinaisons = list(itertools.product(SCENARIOS, TTC_WATCH, CI_DANGER, DRAC_DANGER))
    total_runs = len(combinaisons)
    
    print("=" * 60)
    print(f" LANCEMENT DU GRID SEARCH ({total_runs} simulations)")
    print("=" * 60)

    # Création de l'en-tête du fichier maître
    en_tetes = ["iteration", "scenario", "ttc_watch", "ci_danger", "drac_danger", 
                "profil_tm", "seed", "statut_fin", "arrive", "temps_arrivee_s", 
                "vitesse_moyenne_kmh", "distance_parcourue_m", "n_collisions", 
                "n_freinages", "niveau_max"]
    
    with open(fichier_maitre, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(en_tetes)

    for i, (scen, ttc, ci, drac) in enumerate(combinaisons, 1):
        print(f"\n[Run {i}/{total_runs}] Scen:{scen} | TTC:{ttc}s | CI:{ci} | DRAC:{drac}")
        
        cmd = [
            "python", SCRIPT_CIBLE,
            "--scenario", str(scen),
            "--direction", "droite",
            "--distance", str(DISTANCE_TEST),
            "--dist-arret", "2.0", 
            "--dist-reprise", "3.0", 
            "--proximite-critique", "2.0", 
            "--blocage-max-s", "120.0",
            "--ttc-watch", str(ttc),
            "--ci-danger", str(ci),
            "--drac-danger", str(drac),
            "--no-hud" 
        ]
        
        try:
            t_debut = time.time()
            # On laisse tourner et on accepte les codes d'erreur si la voiture est bloquée
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=300)
            t_fin = time.time()
            
            if result.returncode == 0:
                print(f" -> Succès (Arrivée) en {t_fin - t_debut:.1f}s")
            else:
                print(f" -> Échec (Bloqué/Timeout) en {t_fin - t_debut:.1f}s - Données enregistrées.")
            
            # Lecture et consolidation du petit CSV généré par l'itération
            resumes = list(log_dir.glob("*_resume.csv"))
            if resumes:
                dernier_resume = max(resumes, key=os.path.getctime)
                
                with open(dernier_resume, "r", encoding="utf-8") as rf:
                    reader = list(csv.reader(rf))
                    if len(reader) >= 2:
                        ligne_resultat = reader[-1]
                        with open(fichier_maitre, "a", newline="", encoding="utf-8") as mf:
                            m_writer = csv.writer(mf)
                            m_writer.writerow([i] + ligne_resultat)
                
                os.remove(dernier_resume)
                
        except subprocess.TimeoutExpired:
            print(f" -> TIMEOUT EXTRÊME: CARLA a freezé lourdement. On passe au suivant.")
        except Exception as e:
            print(f" -> ERREUR INCONNUE: {e}")

    print("\n" + "=" * 60)
    print(f"GRID SEARCH TERMINÉ ! Résultats consolidés dans : {fichier_maitre}")
    print("=" * 60)

if __name__ == "__main__":
    main()