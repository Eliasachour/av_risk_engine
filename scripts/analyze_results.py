#!/usr/bin/env python3
import pandas as pd
from pathlib import Path

def analyser_resultats_ponderes():
    log_dir = Path("logs")
    fichiers = list(log_dir.glob("master_grid_search_*.csv"))
    
    if not fichiers:
        print("Aucun fichier de résultats trouvé.")
        return
        
    # Prend le fichier CSV le plus récent
    dernier_fichier = max(fichiers, key=lambda f: f.stat().st_ctime)
    print(f"Analyse du fichier : {dernier_fichier.name}\n")
    
    df = pd.read_csv(dernier_fichier)
    
    # On ne garde que les trajets où la voiture est arrivée à destination
    df_succes = df[df['statut_fin'] == 'arrive'].copy()
    
    if df_succes.empty:
        print("Aucune combinaison n'a permis d'atteindre l'arrivée.")
        return

    print("=" * 65)
    print("MEILLEURS SEUILS PAR SCÉNARIO (Champions Locaux)")
    print("=" * 65)
    
    # Analyse individuelle par scénario
    for scen in [3, 4]:
        df_scen = df_succes[df_succes['scenario'] == scen]
        if not df_scen.empty:
            df_trie = df_scen.sort_values(
                by=['n_collisions', 'n_freinages', 'vitesse_moyenne_kmh'], 
                ascending=[True, True, False]
            )
            top1 = df_trie.iloc[0]
            print(f"\nTOP 1 - SCÉNARIO {scen} :")
            print(f"TTC: {top1['ttc_watch']}s | CI: {top1['ci_danger']} | DRAC: {top1['drac_danger']}")
            print(f"-> Vitesse: {top1['vitesse_moyenne_kmh']:.1f} km/h | Freinages: {top1['n_freinages']} | Collisions: {top1['n_collisions']}")
        else:
            print(f"\nSCÉNARIO {scen} : Aucun succès enregistré (environnement trop strict).")

    print("\n" + "=" * 65)
    print(" 🌟 TOP 5 GLOBAL (Pondéré sur la robustesse inter-scénarios)")
    print("=" * 65)
    
    # Groupement par combinaison exacte d'hyperparamètres
    colonnes_group = ['ttc_watch', 'ci_danger', 'drac_danger']
    
    # Agrégation et pondération des résultats
    df_global = df_succes.groupby(colonnes_group).agg(
        scenarios_reussis=('scenario', 'nunique'), # Vise 2 (réussite sur Scen 3 ET 4)
        collisions_totales=('n_collisions', 'sum'),
        freinages_moyens=('n_freinages', 'mean'),
        vitesse_moyenne_globale=('vitesse_moyenne_kmh', 'mean')
    ).reset_index()
    
    # Tri pondéré : 
    # 1. Moins de collisions cumulées (priorité absolue à la sécurité)
    # 2. Plus grand nombre de scénarios réussis (priorité à la robustesse)
    # 3. Moins de freinages en moyenne (confort)
    # 4. Vitesse moyenne la plus haute (fluidité du trafic)
    df_global_trie = df_global.sort_values(
        by=['collisions_totales', 'scenarios_reussis', 'freinages_moyens', 'vitesse_moyenne_globale'],
        ascending=[True, False, True, False]
    )
    
    # Formatage pour un affichage propre
    df_global_trie['freinages_moyens'] = df_global_trie['freinages_moyens'].round(1)
    df_global_trie['vitesse_moyenne_globale'] = df_global_trie['vitesse_moyenne_globale'].round(1)
    
    print(df_global_trie.head(5).to_string(index=False))

if __name__ == "__main__":
    analyser_resultats_ponderes()