# Démarrage CARLA — Étape 1 (perception + HUD)

Ce guide couvre le lancement de la boucle CARLA de bout en bout : formulaire →
spawn → HUD Pygame temps réel + log CSV.

## Prérequis

**CARLA 0.9.15** installé et démarrable (sous Linux : `./CarlaUE4.sh`).

**Paquets Python** — sur la machine où tourne le client :
```bash
python3 -m pip install pygame numpy
# CARLA Python API : installer le wheel fourni avec CARLA
python3 -m pip install <CARLA>/PythonAPI/carla/dist/carla-0.9.15-cp310-cp310-linux_x86_64.whl
```

Le paquet `carla` n'est **pas** installable via pip standard — il faut utiliser
le wheel livré avec ta version de CARLA, dans `PythonAPI/carla/dist/`. Le nom
exact du wheel dépend de ta version Python (cp38, cp310, cp311).

## Lancement

**Terminal 1** — serveur CARLA :
```bash
cd <CARLA>
./CarlaUE4.sh -quality-level=Low -RenderOffScreen
```
(les flags allègent le rendu ; sur une machine puissante tu peux les omettre)

**Terminal 2** — client (dans le dossier `av_risk_engine`) :
```bash
python3 carla_run.py
```

Un formulaire tkinter s'ouvre :
- **Onglet CARLA** : hôte/port du serveur, carte (Town01 à Town10HD), tick rate.
- **Onglet Scénario** : préréglage SC-XX (facultatif) ou config manuelle
  (route, environnement, ego, agents au format JSON).
- **Onglet Contrôle** : durée max, log CSV activé/désactivé.

Clique **Lancer sur CARLA**. La fenêtre se ferme, Pygame ouvre le HUD :
- **Bandeau supérieur** coloré selon le niveau de risque, vitesse ego, temps.
- **Vue caméra** RGB de l'ego (fond).
- **Panneau latéral droit** : agent le plus critique, ses métriques (TTC, THW,
  DRAC, RSS).
- **Bandeau inférieur** : diagnostic ; devient rouge pulsant en CRITICAL.

Raccourcis : **ESC** quitte, **ESPACE** met en pause.

## Logs

Si activés dans le formulaire, un fichier `logs/carla_YYYYMMDD_HHMMSS.csv` est
créé avec une ligne par tick : `t, niveau_global, vitesse_ego_kmh, n_agents,
ttc_min, drac_max, distance_min, collision`.

Le format est directement importable dans pandas/Excel pour produire des figures
a posteriori.

## À noter à cette étape

- **L'ego ne pilote pas encore.** Une vitesse cible lui est donnée au spawn,
  puis CARLA le laisse tel quel (physique passive). C'est l'étape 2 qui
  branchera `commande_recommandee` pour piloter effectivement l'ego.
- **La configuration est sauvegardée** dans `~/.av_risk_engine/carla_config.json`
  et rechargée au démarrage suivant.

## Dépannage

- **`RuntimeError: time-out of 10000ms while waiting for the simulator`** — le
  serveur CARLA n'est pas encore prêt ou tourne sur un autre port. Vérifie
  `host` et `port` dans le formulaire.
- **`Spawn refusé`** dans la console — le point de spawn est occupé. Relance,
  ou change de carte.
- **HUD noir** — la caméra n'a pas encore reçu de frame. Attends 1-2 secondes.
- **Blueprint introuvable** (`walker.pedestrian.0002`) — certaines versions de
  CARLA n'ont pas tous les blueprints. Édite `world/carla_bridge.py`,
  dictionnaire `BLUEPRINTS`, et remplace par un blueprint disponible dans ta
  version (`walker.pedestrian.0001` existe partout).
