# av_risk_engine

Moteur d'évaluation du risque pour véhicule autonome, conçu autour de CARLA mais
**entièrement utilisable sans lui**. Il transforme une situation de conduite en un
niveau de risque (SAFE / WATCH / DANGER / CRITICAL) en combinant six métriques de
criticité, les contextualise (météo, usager, visibilité), et explique son verdict.

## Démarrage rapide

```bash
python3 -m pip install -r requirements.txt   # pytest, matplotlib, pillow
python3 run.py            # formulaire -> évaluation du risque
python3 simulate.py       # formulaire -> simulation + figures
python3 simulate.py --demo --gif --reaction  # démo sans formulaire
python3 calibrate.py      # calibration sur les scénarios de référence
python3 optimize.py       # optimisation des seuils (proposition avant/après)
python3 -m pytest -q      # la suite de tests (89)
```

### Interface web (React + FastAPI)

```bash
# Terminal 1 — backend (port 8000)
python3 api.py
# Terminal 2 — frontend (port 5173)
cd web && npm install && npm run dev
```

Tableau de bord à trois panneaux : scénario (avec préréglages SC-01..24 et
cohérence automatique des paramètres), évaluation à t = 0 en temps réel, et
simulation (vue de dessus animée + graphes agrandissables). Guide de
déploiement Render dans `web/README.md` — démo en ligne :
backend https://av-risk-engine.onrender.com

Options de `simulate.py` : `--demo` (scénario intégré), `--reaction` (l'ego freine),
`--gif` (vue de dessus animée), `--agent N` (n'afficher que la courbe de l'agent N),
`--no-open` (ne pas ouvrir les figures).

## Principe

```
contexte -> métriques -> modificateurs contextuels -> grille de décision -> niveau -> commande
```

La décision est le **pire** niveau parmi les six métriques (priorité sécurité), et
une couche de pondération indique en plus **quelle métrique pèse le plus**.

## Rôle et importance de chaque fichier

### Racine — points d'entrée
- **run.py** — orchestrateur : ouvre le formulaire, évalue le risque. Squelette de la future boucle CARLA.
- **simulate.py** — chaîne complète : scénario -> simulation cinématique -> table des métriques, impact et figures. Le point d'entrée le plus utilisé pour observer le système.
- **demo.py** — scénario de démonstration minimal en console.
- **calibrate.py** — lance la calibration sur SC-01..06 : table prédit/attendu, matrice de confusion. Pièce de validation.
- **conftest.py / pytest.ini** — configuration des tests. **requirements.txt** — dépendances.

### risk_engine/ — le cœur (indépendant de CARLA, donc testable)
- **context.py** — *fondation* : les dataclasses `ScenarioContext` et `Agent` et les énumérations. Définit les 14 paramètres d'entrée et refuse à la construction les valeurs négatives.
- **metrics.py** — *calcul pur* : les six métriques (TTC à vitesse et à accélération constantes, THW, PET, DRAC, distance RSS, CI composite). Aucune dépendance au contexte d'exécution.
- **modifiers.py** — *contextualisation* : friction µ, facteur usager vulnérable, classe et facteur de visibilité, incertitude de mesure, et famille de conflit (suivi / croisement / face-à-face).
- **engine.py** — *décision* : classe chaque métrique selon `RiskConfig`, retient le pire niveau, identifie la métrique déclencheuse, et calcule la contribution de chaque métrique. C'est le chef d'orchestre.
- **weighting.py** — *pondération* : criticité normalisée [0,1] par métrique et pertinence contextuelle (par famille de conflit) ; produit le classement d'impact. Répond à « quelle métrique pèse le plus ».
- **sanitize.py** — *robustesse* : borne les entrées hors plage physique (vitesses, accélérations, caps, NaN/inf) et signale chaque correction, sans bloquer.
- **report.py** — *présentation* : assemble les métriques de tous les agents en une table lisible et un résumé d'impact.

### scenarios/ — la saisie
- **form.py** — formulaire tkinter, organisé en sections (routiers, environnementaux, véhicule ego, usagers). Saisit un scénario et l'option de freinage.
- **constraints.py** — règles de cohérence (météo ↔ état de route, limites selon le type de route) qui empêchent les scénarios incohérents.

### world/ — l'adaptateur CARLA
- **extraction.py** — *clé du découplage* : géométrie pure (poses -> distance / cap -> contexte), réutilisée à l'identique par le simulateur interne et par CARLA.
- **weather.py** — conversion du contexte en paramètres météo CARLA.
- **carla_world.py** — glu CARLA (connexion, spawn, lecture du monde) ; nécessite `carla` et un GPU.

### sim/ — le simulateur (sans CARLA)
- **kinematic.py** — simulateur cinématique 2D : fait évoluer le scénario, réévalue le risque à chaque pas, et fait freiner l'ego dans la limite de l'adhérence µ·g.
- **visualize.py** — figures matplotlib : métriques par agent dans le temps, comparaison avec/sans freinage, vue de dessus animée. Backend non interactif (pas de crash sans écran).

### calibration/ — la validation
- **scenarios_ref.py** — les six scénarios de référence SC-01..06 et leur niveau attendu (vérité terrain, ajustable).
- **evaluate.py** — compare prédit vs attendu : matrice de confusion et distinction détections manquées / fausses alarmes.

### tests/ — 89 tests
Couvrent métriques, moteur, grille de seuils, pondération, assainissement, contraintes, extraction, météo, simulateur et calibration.

## Note CARLA
CARLA n'est requis que pour `world/carla_world.py`. Le reste tourne et se teste sans
lui. Version recommandée : CARLA 0.9.15 (Linux + GPU).
