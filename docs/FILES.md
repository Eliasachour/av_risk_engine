# Référence des fichiers — av_risk_engine

Rôle de chaque fichier du projet, regroupé par paquet. Le principe directeur :
le **moteur de risque** (`risk_engine/`) est pur et indépendant de CARLA et de
tkinter — c'est ce qui le rend testable, calibrable et réutilisable.

## Points d'entrée (`apps/`)

Tous les scripts exécutables sont regroupés dans `apps/`. Chacun ajoute
automatiquement la racine du dépôt au `sys.path` (préambule court en tête), ce
qui permet de les lancer directement (`python3 apps/foo.py`) tout en gardant les
imports métier propres.

- **apps/run.py** — orchestrateur minimal : ouvre le formulaire, évalue le risque du
  scénario saisi. Squelette historique de la future boucle CARLA.
- **apps/simulate.py** — chaîne complète : scénario → simulation → table des métriques,
  seuils, impact et figures. Options : `--demo`, `--reaction`, `--gif`, `--monde`
  (repère absolu), `--agent N`, `--no-open`. Le point d'entrée le plus utilisé.
- **apps/demo.py** — scénario de démonstration minimal en console (sans formulaire).
- **apps/calibrate.py** — lance la calibration sur les scénarios de référence : table
  prédit/attendu, matrice de confusion, synthèse. `--details` pour le détail par métrique.
- **apps/optimize.py** — optimisation des seuils par descente par coordonnées sous
  contrainte dure « zéro détection manquée », puis minimisation des fausses alarmes.
  Affiche l'avant/après et les seuils modifiés (proposition, rien n'est écrit).
- **apps/api.py** — API web FastAPI exposant le moteur : `/enums`, `/presets`,
  `/contraintes` (règles de cohérence), `/seuils`, `/evaluate` (t = 0) et
  `/simulate` (frames complètes). Gestion d'erreurs propre (entrées invalides →
  400 lisible), CORS ouvert. Sert de backend à l'interface web (`web/`) et de
  démonstration du découplage du moteur. Déployée sur Render.
- **apps/carla_run.py** — session CARLA interactive : formulaire tkinter →
  contexte → boucle synchrone avec `commande_recommandee` → HUD Pygame + log CSV.
- **apps/carla_freedrive.py** — mode conduite libre : menu Pygame, trafic IA,
  conduite au clavier, moteur en observation avec trois niveaux d'assistance
  jusqu'à l'AEB. Météo modifiable en cours de route.
- **apps/carla_replay.py** — rejeu des scénarios de référence dans CARLA, avec
  bilan CSV comparant niveau prédit vs niveau observé max. Modes `--preset SC-XX`
  ou `--all --headless` (batch des 24).

À la racine (hors `apps/`) : **conftest.py**, **pytest.ini** (configuration des
tests), **requirements.txt** (dépendances), **README.md** (démarrage rapide).

## risk_engine/ — le cœur (pur, sans CARLA ni tkinter)

- **context.py** — *fondation*. Dataclasses `ScenarioContext` et `Agent`, et les
  énumérations (`TypeRoute`, `Geometrie`, `EtatRoute`, `Meteo`, `Heure`, `TypeAgent`).
  Définit les 14 paramètres d'entrée ; refuse à la construction les valeurs négatives.
- **metrics.py** — *calcul pur des métriques*. `to_ms`, `closing_speed`, `ttc`
  (vitesse constante), `ttc_accel` (accélération constante, avec garde d'arrêt), `thw`,
  `drac`, `braking_distance`, `pet`, `conflict_index` (CI composite), `rss_min_distance`.
- **modifiers.py** — *contextualisation*. `friction_multiplier` et `mu` (adhérence
  selon l'état de route), `agent_factor` (usager vulnérable), `classe_visibilite` /
  `visibility_factor`, `uncertainty_factor` (profondeur mesurée vs inférée), et
  `famille_conflit` (suivi / croisement / face-à-face à partir du cap).
- **engine.py** — *décision*. `RiskLevel` (4 niveaux), `RiskConfig` (tous les seuils),
  `AgentRisk` et `RiskAssessment` (résultats), `_band_haut` / `_band_bas` (classement),
  `assess_agent` (six métriques → marge contextuelle → pire niveau + déclencheur +
  contributions) et `assess_risk` (assainit puis agrège les agents).
- **weighting.py** — *pondération*. `POIDS` (pertinence par famille de conflit),
  `criticite_haut` / `criticite_bas` (criticité normalisée [0,1]), `contributions`
  (pertinence × criticité) et `classement` (métriques par impact décroissant).
- **sanitize.py** — *robustesse*. `sanitize_agent` et `sanitize_context` : bornent les
  entrées hors plage physique (vitesses, distances, accélérations, caps, NaN/inf) et
  renvoient la liste des corrections, sans rejeter.
- **geometry.py** — *géométrie relative*. `pose_agent_relative` et
  `vitesse_agent_relative` : conversion (distance, écart latéral, cap) → pose 2D
  dans le repère ego. **Partagée avec `sim/kinematic.py`** : le moteur et le
  simulateur placent les agents à l'identique, condition pour que le PET
  géométrique (D15) évalue bien la trajectoire que le simulateur affiche.
- **control.py** — *commande recommandée* (`commande_recommandee`, `CommandeEgo`,
  `ObsAgent`). Traduit une évaluation de risque en commande véhicule prête à
  appliquer (accélération m/s², throttle/brake ∈ [0,1], mode). Freinage physique
  quand un agent est dans la voie devant (décélération requise, plafond µ·g),
  proportionnel au niveau sinon. Utilisée à l'identique par le simulateur
  interne et par la glu CARLA — c'est le point de pivot du contrôleur.
- **report.py** — *présentation*. `metriques_agent` / `tableau_metriques` (assemble les
  métriques par agent), `lignes_tableau`, `format_tableau` (table console),
  `format_seuils` (grille de référence des seuils), `format_impact` (résumé d'impact).
- **__init__.py** — expose l'API publique du paquet.

## scenarios/ — la saisie

- **form.py** — formulaire tkinter, organisé en sections (routiers, environnementaux,
  véhicule ego, usagers). Fenêtre « métriques » avec table colorée par niveau et grille
  des seuils de référence. Compose un `ScenarioContext` et l'option de freinage.
- **constraints.py** — règles de cohérence (météo ↔ état de route, limites ↔ type de
  route) qui empêchent les scénarios incohérents à la saisie.

## world/ — l'adaptateur CARLA

- **extraction.py** — *clé du découplage*. `ActorState`, `AgentObservation`,
  `planar_distance`, `relative_heading_deg`, `agent_from_observation`, `refresh_context` :
  géométrie pure (poses → distance / cap → contexte), réutilisée à l'identique par le
  simulateur interne et par CARLA.
- **weather.py** — `to_carla_weather` : convertit le contexte en paramètres météo CARLA.
- **carla_bridge.py** — pont de perception CARLA. `CarlaBridge` (context manager) :
  connexion, chargement de carte, passage en mode synchrone, spawn ego + agents,
  tick, conversion `carla.Actor → AgentObservation` pour `refresh_context`.
  Nettoie automatiquement les acteurs et restaure le mode asynchrone en sortie.
- **env_sensors.py** — capteurs d'environnement : `DetecteurObstacle`
  (`sensor.other.obstacle`, détecte la géométrie **statique** de la carte — murs,
  glissières, façades — invisible à la perception d'acteurs), `DetecteurCollision`
  (impacts réels et leur intensité), et `contexte_route` (limite de vitesse,
  géométrie, feu tricolore lus dans la carte à chaque tick).
- **perception_oracle.py** — vérité terrain CARLA filtrée par rayon et cône de
  vision, avec classification blueprint → `TypeAgent`. Le caractère « oracle »
  est explicite dans le HUD : ce n'est pas une chaîne perception réelle.
- **traffic.py** — `GestionnaireTrafic` : spawn de véhicules IA (Traffic Manager)
  et de piétons IA (Walker AI Controllers), nettoyage garanti à la sortie.
- **keyboard_control.py** — conduite au clavier avec rampes anti-à-coups.
- **aeb.py** — machine à états d'assistance : évaluation, alerte, freinage
  d'urgence automatique sur CRITICAL persistant.
- **carla_control.py** — helpers de contrôle hors moteur : `pilotage_lateral`
  (suivi de voie via waypoint CARLA) et `reprise_acc` (retour à la vitesse cible
  en SAFE). Utilisés par `apps/carla_run.py` et `apps/carla_replay.py`. Le
  pilotage latéral est délibérément hors de `risk_engine/control.py` (D11).
- **carla_form.py** — formulaire tkinter de configuration CARLA à trois onglets
  (Serveur / Scénario / Contrôle) avec chargement des préréglages SC-XX.
- **carla_world.py** — ancienne glu CARLA (superseded par carla_bridge.py).
- **hud/** — sous-package du HUD Pygame :
  - **state.py** : dataclass `HUDState` (contrat entre le point d'entrée et le rendu).
  - **palette.py** : couleurs par niveau, dimensions du HUD, polices.
  - **pygame_hud.py** : classe `HUD` (bandeau supérieur avec pastilles de
    contexte routier, panneau agents, panneau des six métriques chiffrées,
    bandeau inférieur avec alerte pulsante, panneau d'aide clavier).
  - **menu.py** : menu de configuration au clavier, rendu dans la **même
    fenêtre** que le HUD — plus de formulaire séparé.
  - **weather_control.py** : météo pilotable en direct (7 préréglages F1–F7 et
    réglages fins). Met à jour le contexte du moteur *et* la friction des pneus,
    pour que le simulé et l'évalué ne divergent pas.
  - **minimap.py** : mini-carte radar top-down.

## sim/ — le simulateur (sans CARLA)

- **kinematic.py** — simulateur cinématique 2D. `FREINAGE` (décélérations visées par
  niveau), `Frame`, `_init` (placement, avec écart latéral), `_advance` (point-masse),
  `_dans_la_voie_devant` (test géométrique de conflit en voie), `run` (boucle : contexte
  → risque → **freinage d'urgence différencié** plafonné à µ·g → avance), `collision`.
- **visualize.py** — figures matplotlib. `plot_metrics` (métriques par agent dans le
  temps), `plot_comparaison` (avec / sans réaction), `animate_topdown` (vue de dessus
  animée, repère ego ou absolu), palette `COULEURS` par niveau. Backend non interactif.

## calibration/ — la validation

- **scenarios_ref.py** — les 24 scénarios de référence (SC-01 à SC-24) et leur niveau
  attendu (vérité terrain), plus les fabriques compactes `_ag` / `_ctx`.
- **evaluate.py** — `evaluer` (prédit vs attendu, paramétré par la config),
  `matrice_confusion`, `synthese` (détections manquées / fausses alarmes / exactitude),
  `format_rapport`.
- **BASELINE_v1.md** — le point de départ de calibration, figé et documenté.
- **CHANGELOG.md** — journal complet des évolutions (v0.1 → v1.7) : chaque
  changement, sa justification, son effet mesuré sur les trois compteurs.
- **ETIQUETAGE.md** — le référentiel d'étiquetage (4 règles reproductibles :
  inévitabilité, graduation TTC, durcissement contextuel en zone tendue,
  correction géométrique latérale) et ses limites assumées.
- **__init__.py** — expose l'API de calibration.

## web/ — l'interface web (React + Vite + TypeScript)

Tableau de bord à trois panneaux redimensionnables (largeurs persistées),
branché sur `api.py`. Preuve vivante du découplage : troisième interface du
même moteur (après la console et tkinter), sans une ligne dupliquée.

- **src/App.tsx** — orchestration : évaluation temps réel (debounce 300 ms,
  annulation des requêtes en vol), barre supérieure avec statut API et messages
  d'erreur, splitters de redimensionnement.
- **src/components/ScenarioForm.tsx** — formulaire complet (route, environnement,
  ego, agents avec écart latéral et accélération), préréglages SC-01..24, et
  **cohérence automatique des paramètres** (météo → états de route compatibles,
  visibilité plausible, limites par type de route) servie par `/contraintes`.
- **src/components/InstantResults.tsx** — niveau global (pulsation en CRITICAL),
  six cartes de métriques avec jauges, badges et info-bulles des seuils,
  déclencheur/impact, barres de contribution et corroboration.
- **src/components/Simulation.tsx** — vue de dessus SVG animée (traces, halo de
  freinage, repère ego/monde, route courbée en virage) et quatre graphes
  (distance vs RSS, TTC/THW avec seuils, DRAC vs µ·g, vitesse + niveau), chacun
  **agrandissable en modal**, avec timeline lecture auto + curseur manuel.
- **src/api.ts / src/types.ts** — client API (AbortController, timeout, erreurs
  lisibles) et types miroirs des dataclasses. URL de production Render intégrée.
- **README.md** — démarrage local et guide de déploiement Render.

## tests/ — 125 tests

Couvrent : métriques (`test_metrics`), moteur (`test_engine`), grille de seuils
(`test_thresholds`), pondération (`test_weighting`), assainissement (`test_sanitize`),
contraintes de saisie (`test_constraints`), extraction géométrique (`test_extraction`),
météo (`test_weather`), simulateur (`test_kinematic`), présentation (`test_report`),
calibration (`test_calibration`), optimiseur (`test_optimize`) et **invariants du
moteur** (`test_invariants` : 10 propriétés — monotonie en distance, sévérité accrue
sur sol dégradé / de nuit / pour un VRU / en profondeur inférée, niveau global = pire
agent, filtrage latéral jamais amplifiant, agent qui s'éloigne = SAFE, NaN toléré,
obstacle inévitable = CRITICAL).
