# av_risk_engine

Moteur d'évaluation du risque pour véhicule autonome, conçu autour de CARLA mais
**entièrement utilisable sans lui**. Il transforme une situation de conduite en un
niveau de risque (SAFE / WATCH / DANGER / CRITICAL) en combinant six métriques de
criticité, les contextualise (météo, usager, visibilité), et explique son verdict.

## Démarrage rapide

```bash
python3 -m pip install -r requirements.txt   # pytest, matplotlib, pillow, fastapi, uvicorn
python3 apps/run.py            # formulaire -> évaluation du risque
python3 apps/simulate.py       # formulaire -> simulation + figures
python3 apps/simulate.py --demo --gif --reaction  # démo sans formulaire
python3 apps/calibrate.py      # calibration sur les scénarios de référence
python3 apps/optimize.py       # optimisation des seuils (proposition avant/après)
python3 -m pytest -q           # la suite de tests (125)
```

### Interface web (React + FastAPI)

```bash
# Terminal 1 — backend (port 8000)
python3 apps/api.py
# Terminal 2 — frontend (port 5173)
cd web && npm install && npm run dev
```

Tableau de bord à trois panneaux : scénario (avec préréglages SC-01..24 et
cohérence automatique des paramètres), évaluation à t = 0 en temps réel, et
simulation (vue de dessus animée + graphes agrandissables). Guide de
déploiement Render dans `web/README.md` — démo en ligne :
backend https://av-risk-engine.onrender.com

### Intégration CARLA

```bash
python3 apps/carla_run.py         # session interactive avec HUD Pygame
python3 apps/carla_replay.py --preset SC-05 --duree 15   # rejouer un scénario
python3 apps/carla_replay.py --all --headless            # batch des 24 scénarios
```

Voir `docs/CARLA_DEMARRAGE.md` pour le guide complet.

## Principe

```
contexte -> métriques -> modificateurs contextuels -> grille de décision -> niveau -> commande
```

La décision est le **pire** niveau parmi les six métriques (priorité sécurité), et
une couche de pondération indique en plus **quelle métrique pèse le plus**.

## Structure du dépôt

```
av_risk_engine/
├── apps/               # points d'entrée exécutables
│   ├── api.py            # backend FastAPI de l'interface web
│   ├── run.py            # formulaire tkinter -> évaluation
│   ├── simulate.py       # simulation cinématique + figures
│   ├── calibrate.py      # calibration sur SC-01..24
│   ├── optimize.py       # optimisation des seuils
│   ├── demo.py           # démo minimale en console
│   ├── carla_run.py      # session CARLA interactive
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
```

Le détail par fichier est dans `docs/FILES.md`, le détail des tests dans
`docs/TESTS.md`, l'historique des choix dans `docs/DECISIONS.md`.

## Note CARLA
CARLA n'est requis que pour `world/carla_bridge.py` et les points d'entrée
`apps/carla_*.py`. Le reste tourne et se teste sans lui. Version recommandée :
CARLA 0.9.15 (Linux + GPU).
