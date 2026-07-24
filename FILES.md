# Référence des fichiers — av_risk_engine

Rôle de chaque fichier du projet, regroupé par paquet. Le principe directeur :
le **moteur de risque** (`risk_engine/`) est pur et indépendant de CARLA et de
tkinter — c'est ce qui le rend testable, calibrable et réutilisable.

## Points d'entrée (racine)

- **run.py** — orchestrateur minimal : ouvre le formulaire, évalue le risque du
  scénario saisi. Squelette de la future boucle CARLA.
- **simulate.py** — chaîne complète : scénario → simulation → table des métriques,
  seuils, impact et figures. Options : `--demo`, `--reaction`, `--gif`, `--monde`
  (repère absolu), `--agent N`, `--no-open`. Le point d'entrée le plus utilisé.
- **demo.py** — scénario de démonstration minimal en console (sans formulaire).
- **calibrate.py** — lance la calibration sur les scénarios de référence : table
  prédit/attendu, matrice de confusion, synthèse. `--details` pour le détail par métrique.
- **optimize.py** — optimisation des seuils par descente par coordonnées sous
  contrainte dure « zéro détection manquée », puis minimisation des fausses alarmes.
  Affiche l'avant/après et les seuils modifiés (proposition, rien n'est écrit).
- **api.py** — API web FastAPI exposant le moteur : `/enums`, `/presets`,
  `/contraintes` (règles de cohérence), `/seuils`, `/evaluate` (t = 0) et
  `/simulate` (frames complètes). Gestion d'erreurs propre (entrées invalides →
  400 lisible), CORS ouvert. Sert de backend à l'interface web (`web/`) et de
  démonstration du découplage du moteur. Déployée sur Render.
- **conftest.py**, **pytest.ini** — configuration de la suite de tests.
- **requirements.txt** — dépendances (pytest, matplotlib, pillow).
- **README.md** — présentation générale et démarrage rapide.

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
- **weather.py** — `weather_params` : convertit le contexte en paramètres météo CARLA.
- **carla_world.py** — glu CARLA (connexion, spawn, lecture du monde) ; nécessite le
  paquet `carla` et un GPU.

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

## tests/ — 89 tests

Couvrent : métriques (`test_metrics`), moteur (`test_engine`), grille de seuils
(`test_thresholds`), pondération (`test_weighting`), assainissement (`test_sanitize`),
contraintes de saisie (`test_constraints`), extraction géométrique (`test_extraction`),
météo (`test_weather`), simulateur (`test_kinematic`), présentation (`test_report`),
calibration (`test_calibration`), optimiseur (`test_optimize`) et **invariants du
moteur** (`test_invariants` : 10 propriétés — monotonie en distance, sévérité accrue
sur sol dégradé / de nuit / pour un VRU / en profondeur inférée, niveau global = pire
agent, filtrage latéral jamais amplifiant, agent qui s'éloigne = SAFE, NaN toléré,
obstacle inévitable = CRITICAL).
