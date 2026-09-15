# av_risk_engine

Moteur d'évaluation du risque pour véhicule autonome, conçu autour de CARLA mais **entièrement utilisable sans lui**. Il transforme une situation de conduite en un niveau de risque (SAFE / WATCH / DANGER / CRITICAL) en combinant six métriques de criticité, les contextualise (météo, usager, visibilité), et explique son verdict.

## 🛠️ Démarrage rapide (Sans CARLA)

` ` `bash
python3 -m pip install -r requirements.txt   # pytest, matplotlib, pillow, fastapi, uvicorn
python3 apps/run.py            # formulaire -> évaluation du risque
python3 apps/simulate.py       # formulaire -> simulation + figures
python3 apps/simulate.py --demo --gif --reaction  # démo sans formulaire
python3 apps/calibrate.py      # calibration sur les scénarios de référence
python3 apps/optimize.py       # optimisation des seuils (proposition avant/après)
python3 -m pytest -q           # la suite de tests (125)
` ` `

### Interface web (React + FastAPI)

` ` `bash
# Terminal 1 — backend (port 8000)
python3 apps/api.py
# Terminal 2 — frontend (port 5173)
cd web && npm install && npm run dev
` ` `

Tableau de bord à trois panneaux : scénario (avec préréglages SC-01..24 et cohérence automatique des paramètres), évaluation à t = 0 en temps réel, et simulation (vue de dessus animée + graphes agrandissables). Guide de déploiement Render dans `web/README.md` — démo en ligne : backend https://av-risk-engine.onrender.com

---

## 🚀 Intégration et Lancement avec CARLA

Pour évaluer le moteur de risque en temps réel dans la simulation 3D, voici la procédure complète.

### 1. Préparation de l'environnement Python
Ouvrez un terminal et placez-vous à la racine de ce projet (`av_risk_engine`), puis activez votre environnement virtuel :
` ` `bash
# Windows
.\.venv-carla-12\Scripts\Activate.ps1
# Linux / macOS
source .venv-carla-12/bin/activate
` ` `
**Pourquoi utiliser un environnement virtuel ?** 
Le projet requiert des dépendances très spécifiques (comme l'API Python de `carla`, `pygame` pour le HUD, `pandas` pour l'analyse). L'environnement virtuel agit comme une bulle hermétique : il garantit que ces librairies n'entreront pas en conflit avec d'autres projets sur votre machine, tout en assurant une exécution stable des scripts.

### 2. Démarrer le Simulateur CARLA
Le code Python ne lance pas le jeu lui-même, il ne fait que s'y connecter.
Ouvrez un **second terminal**, naviguez jusqu'à votre dossier d'installation de CARLA (ex: `CARLA_0.9.16`) et lancez le simulateur :

` ` `bash
# Windows
.\CarlaUE4.exe
# Linux
./CarlaUE4.sh
` ` `

**💡 Astuce - Lancer CARLA de manière optimisée :**
Si votre PC ralentit ou que la simulation saccade, vous pouvez lancer CARLA avec des paramètres réduisant drastiquement la charge sur la carte graphique :
` ` `bash
# Qualité basse, mode fenêtré, et rendu allégé
.\CarlaUE4.exe -quality-level=Low -windowed -ResX=800 -ResY=600
` ` `

### 3. Exécution des Scripts
Une fois CARLA ouvert et la ville chargée à l'écran, retournez dans votre **premier terminal** (celui avec l'environnement virtuel activé).

**⚠️ L'astuce du chargement de la carte (Pré-warmup) :**
Lorsque vous lancez un script complexe (comme le Benchmark) qui nécessite une nouvelle carte (ex: *Town03*), CARLA met beaucoup de temps à charger les textures la première fois. Cela provoque souvent une erreur `Timeout of 10000ms`. 
Pour éviter cela, il est conseillé de lancer un script simple une première fois pour forcer le simulateur à charger la ville en mémoire :
` ` `bash
# 1. Lancer un script léger pour charger Town03 tranquillement
python3 apps/carla_run.py 

# 2. Une fois la map chargée, vous pouvez lancer vos lourdes campagnes :
python3 apps/carla_benchmark_v8_opt.py --scenario 3 --distance 2000
` ` `

**Autres commandes CARLA disponibles :**
` ` `bash
python3 apps/carla_run.py                 # session interactive avec HUD Pygame
python3 apps/carla_replay.py --preset SC-05 --duree 15   # rejouer un scénario spécifique
python3 apps/carla_replay.py --all --headless            # batch complet des 24 scénarios
` ` `
Voir `docs/CARLA_DEMARRAGE.md` pour le guide technique approfondi.

---

## 🧠 Principe

` ` `text
contexte -> métriques -> modificateurs contextuels -> grille de décision -> niveau -> commande
` ` `

La décision est le **pire** niveau parmi les six métriques (priorité sécurité), et une couche de pondération indique en plus **quelle métrique pèse le plus**.

## 📁 Structure du dépôt

` ` `text
av_risk_engine/
├── apps/               # points d'entrée exécutables
│   ├── api.py            # backend FastAPI de l'interface web
│   ├── run.py            # formulaire tkinter -> évaluation
│   ├── simulate.py       # simulation cinématique + figures
│   ├── calibrate.py      # calibration sur SC-01..24
│   ├── optimize.py       # optimisation des seuils
│   ├── demo.py           # démo minimale en console
│   ├── carla_run.py      # session CARLA interactive
│   ├── carla_benchmark...# scripts d'évaluation et Grid Search
│   └── carla_replay.py   # rejeu des scénarios dans CARLA
│
├── risk_engine/        # le cœur du moteur (indépendant de CARLA)
│   ├── context.py, metrics.py, modifiers.py
│   ├── engine.py, weighting.py, sanitize.py
│   ├── control.py        # commande recommandée (throttle/brake exportables)
│   ├── lateral.py        # filtrage géométrique 2D
│   └── report.py
│
├── sim/                # simulateur cinématique 2D (sans CARLA)
├── scenarios/          # formulaire tkinter, contraintes de cohérence
├── calibration/        # jeu de référence + méthode d'étiquetage
│
├── world/              # adaptateur CARLA
│   ├── extraction.py     # géométrie pure (partagée sim / CARLA)
│   ├── weather.py        # traduction météo -> WeatherParameters CARLA
│   ├── carla_bridge.py   # pont perception (connexion, spawn, tick)
│   ├── carla_control.py  # pilotage latéral + reprise ACC
│   ├── carla_form.py     # formulaire de configuration CARLA
│   └── hud/              # sous-package du HUD Pygame
│       ├── state.py, palette.py, pygame_hud.py
│
├── web/                # frontend React + Vite + TypeScript
│
├── tests/              # 125 tests (unitaires + invariants + calibration)
│
└── docs/               # toute la documentation
    ├── CHANGELOG.md      # journal projet (phases A → I)
    ├── DECISIONS.md      # registre des 12 décisions techniques
    ├── FILES.md          # référence des fichiers
    ├── TESTS.md          # documentation des 125 tests
    └── CARLA_DEMARRAGE.md
` ` `

Le détail par fichier est dans `docs/FILES.md`, le détail des tests dans `docs/TESTS.md`, l'historique des choix dans `docs/DECISIONS.md`.

## 📌 Note CARLA
CARLA n'est requis que pour `world/carla_bridge.py` et les points d'entrée `apps/carla_*.py`. Le reste tourne et se teste sans lui. Version recommandée : **CARLA 0.9.15** ou **0.9.16** (Linux + GPU ou Windows).
