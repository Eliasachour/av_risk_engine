# Journal des évolutions — av_risk_engine

Historique chronologique des **évolutions du projet dans son ensemble** : moteur,
simulateur, interface, tests, documentation, déploiement. Pour le détail
*spécifique à la calibration* (étiquettes, seuils, résultats sur les 24 scénarios),
voir `calibration/CHANGELOG.md`.

Format : *changement / justification / impact vérifiable*.

---

## Phase A — Le moteur pur (conception)

**A.1 — Grille multi-métriques à quatre niveaux.** Décision par le pire des six
métriques (TTC, THW, PET, RSS, CI, DRAC), avec traçage de la métrique
déclencheuse. Garantit par construction la non sous-estimation du risque.

**A.2 — Contextualisation via TTC effectif.** Marge = friction × usager ×
visibilité × incertitude, appliquée au TTC (pas de double comptage sur les
métriques déjà physiques).

**A.3 — Freinage plafonné à l'adhérence µ·g.** Ratios de friction sec/mouillé/
neigeux/verglas explicites. Distance d'arrêt physiquement cohérente.

**A.4 — Métriques faites au bon niveau de fidélité.** RSS binaire (fidèle à
Shalev-Shwartz), CI composite (imminence × sévérité), TTC à accélération
constante avec garde d'arrêt.

**A.5 — Brique pondération.** Couche `weighting.py` : criticité × pertinence
contextuelle par famille de conflit, expose la métrique la plus impactante et
la corroboration. La décision reste le max (sécurité) ; la pondération sert
l'explicabilité.

**A.6 — Brique assainissement.** Module `sanitize.py` qui borne les valeurs
aberrantes et signale, sans jamais bloquer.

## Phase B — Le simulateur

**B.1 — Écart latéral pour les vraies traversées.** Le champ existait dans la
dataclass mais n'était pas transmis par le formulaire ni utilisé par le
simulateur. Câblé de bout en bout ; un piéton peut désormais démarrer sur le
trottoir et entrer dans la voie.

**B.2 — Vue de dessus multi-agents.** Marqueurs par type, couleur par niveau,
légende. Mode `--monde` (repère absolu) en plus du repère ego, qui supprime la
diagonale trompeuse pour les traversées.

**B.3 — Freinage d'urgence différencié.** Arrêt complet verrouillé si un agent
est *dans la voie devant*, ralentir-puis-reprendre pour un croisement. L'ego ne
flue plus jusqu'au contact.

**B.4 — Freinage fondé sur la physique + diagnostic de collision.** Le
contrôleur commande la décélération *réellement requise* (façon DRAC) plafonnée
à µ·g, robuste au nombre d'agents. Collision détectée image par image (arrêt à
l'impact) et diagnostic évitable / inévitable exposé (« requis 12,3 > µ·g 8,8 »).

## Phase C — Décision géométrique

**C.1 — Filtrage latéral 2D dans la décision** (`risk_engine/lateral.py`).
Facteur de menace fondé sur l'écart latéral projeté à l'horizon TTC ; câblé en
atténuation dans `assess_agent` — rétrograde un agent hors trajectoire de
collision, jamais ne l'amplifie. Règle asymétrique VRU / motorisé documentée.

## Phase D — Calibration et étiquetage

**D.1 — Jeu de calibration élargi (6 → 24 scénarios).** Couverture des trois
familles de conflit × quatre niveaux × conditions dégradées.

**D.2 — Baseline figé** (`BASELINE_v1.md`). Point de départ non réglé, étalon
des évolutions futures.

**D.3 — Optimiseur de seuils sous contrainte** (`apps/optimize.py`). Descente par
coordonnées, contrainte dure « zéro détection manquée », puis minimisation des
fausses alarmes. `rss_violation_level` non optimisable (choix sémantique).

**D.4 — Référentiel d'étiquetage reproductible** (`ETIQUETAGE.md`). Quatre
règles physiques ordonnées : inévitabilité, graduation TTC, durcissement
contextuel *en zone temporelle tendue*, correction géométrique latérale. Rend
chaque étiquette défendable et vérifiable.

*Détail complet des versions de calibration (v1.0 → v1.7) et effets mesurés :
voir `calibration/CHANGELOG.md`.*

## Phase E — Robustesse et invariants

**E.1 — Suite de tests élargie (76 → 89).** Ajout de `test_optimize.py` (garde-
fou de sécurité de l'optimiseur) et de `test_invariants.py` (10 propriétés que
le moteur doit toujours respecter, quelles que soient les évolutions).

**E.2 — Invariants du moteur.** Monotonie en distance, sévérité accrue sur sol
dégradé / de nuit / pour un VRU / en profondeur inférée, niveau global = pire
agent, filtrage latéral jamais amplifiant, agent qui s'éloigne = SAFE, NaN
toléré, obstacle inévitable = CRITICAL. **10 / 10 respectés.**

## Phase F — Interface web

**F.1 — API FastAPI** (`apps/api.py`). Huit endpoints : `/enums`, `/presets`,
`/contraintes`, `/seuils`, `/evaluate`, `/simulate`, `/health`. Gestion
d'erreurs propre — les entrées invalides renvoient 400 avec message lisible
(jamais de 500 silencieux).

**F.2 — Frontend React + Vite + TypeScript** (`web/`). Tableau de bord à trois
panneaux redimensionnables (largeurs persistées en localStorage) : formulaire
scénario (avec préréglages SC-01..24), évaluation à t = 0 en temps réel avec
debounce et annulation des requêtes en vol, simulation avec vue de dessus SVG
animée et quatre graphes agrandissables en modal.

**F.3 — Cohérence servie par l'API.** Les règles météo ↔ état de route,
visibilité plausible, limites par type de route restent dans
`scenarios/constraints.py` (source unique de vérité) et sont **servies** par
`/contraintes`. Le formulaire les applique automatiquement ; `/evaluate` remonte
les incohérences résiduelles comme avertissements.

**F.4 — Vue de dessus enrichie.** Traces fantômes ego + agents, halo pulsant de
freinage, switch repère ego / repère monde, route courbée sinusoïdale en cas
de virage, badge « VIRAGE » et note honnête sur la modélisation 2D linéaire.

**F.5 — Graphes zoomables + tooltips de seuils.** Chaque graphe agrandissable
en modal plein écran ; chaque carte de métrique affiche au survol la grille
des seuils avec description courte, alignée à gauche ou à droite selon la
position pour ne jamais déborder.

**F.6 — Robustesse client.** AbortController par canal (annule la requête
précédente encore en vol), timeout de 15 s, parseur numérique sûr dans le
formulaire (champ vide → 0, plus jamais de NaN envoyé), écran de démarrage
avec indicateur de statut API.

## Phase G — Déploiement

**G.1 — Compatible Render.** `api.ts` détecte l'environnement (proxy Vite en
dev, URL Render en prod, surchargable par `VITE_API_BASE`).
`vite-env.d.ts` autosuffisant pour un `tsc` robuste. `requirements.txt` complété
(fastapi, uvicorn). Backend en ligne :
https://av-risk-engine.onrender.com.

## Phase I — Préparation CARLA

**I.1 — Commande recommandée exportable** (`risk_engine/control.py`). Extraction
de la logique de contrôle (décélération physique dans la voie, plafond µ·g,
freinage proportionnel en croisement) dans un module pur du moteur, avec sortie
normalisée en `throttle` / `brake` ∈ [0,1] directement consommable par
`carla.VehicleControl`. Le simulateur interne consomme la même fonction que la
glu CARLA — source unique de vérité. Aucun changement de comportement (calibration
identique : 0 · 8 · 16/24). 7 tests dédiés verrouillent le contrat public.

**I.2 — Pont de perception CARLA** (`world/carla_bridge.py`). Encapsule la
connexion CARLA (mode synchrone 20 Hz), le spawn ego + agents à partir d'un
`ScenarioContext`, la conversion des `carla.Actor` en `AgentObservation` que
le moteur consomme déjà. Context manager qui restaure le mode asynchrone et
nettoie les acteurs en sortie, même en cas d'exception.

**I.3 — Point d'entrée + formulaire tkinter + HUD Pygame**. Formulaire à 3
onglets (CARLA / Scénario / Contrôle) avec chargement des préréglages SC-XX,
sauvegarde de config dans `~/.av_risk_engine/`. HUD Pygame enrichi : bandeau
supérieur coloré, panneau agents trié par criticité (max 5), panneau jauges
physiques (TTC, THW, DRAC vs µ·g, v_ego vs cible) avec seuils colorés, alerte
pulsante en CRITICAL. Log CSV tick-par-tick.

**I.4 — Boucle de contrôle automatique**. À chaque tick : `refresh_context` →
`assess_risk` → `commande_recommandee` → `VehicleControl`. Freinage physique,
reprise ACC vers la vitesse cible en SAFE, pilotage latéral simple par suivi
de voie via waypoint CARLA. Le champ `steer` reste hors du moteur (limite D11).

**I.5 — Rejouabilité des SC-XX** (`apps/carla_replay.py`). Rejoue un scénario de
référence dans CARLA, compare le niveau observé au niveau prédit par le
moteur, écrit un bilan CSV. Mode `--all --headless` pour un run batch des 24
scénarios : matériau de validation pour le mémoire (accord prédit/observé).

## Phase J — Mode conduite libre

**J.1 — Perception oracle filtrée** (`world/perception_oracle.py`). Traduit les
acteurs CARLA vivants (véhicules du Traffic Manager, piétons IA) en
`AgentObservation` que le moteur consomme. Filtrage par rayon (60 m par défaut)
et par cône de vision avant (±60°). La classification blueprint → `TypeAgent`
distingue voiture, camion, cycliste, piéton, ouvrier. Le HUD affiche
explicitement « perception : oracle » — transparence sur la source de vérité.

**J.2 — Gestion du trafic autonome** (`world/traffic.py`). Context manager qui
spawn N véhicules IA (gérés par le Traffic Manager, avec diversité des vitesses
et respect des feux paramétrable) et M piétons IA (Walker AI Controllers avec
destinations aléatoires). Nettoyage automatique de tous les acteurs à la sortie.

**J.3 — Contrôle clavier** (`world/keyboard_control.py`). WASD/flèches → 
`VehicleControl` avec rampes de throttle/brake pour éviter les à-coups, rappel
de la direction vers zéro, marche arrière et frein à main.

**J.4 — Trois niveaux d'assistance** (`world/aeb.py`). Machine à états
sélectionnable : *évaluation* (moteur observe), *alerte* (visuelle en DANGER/
CRITICAL avec durée minimale d'affichage), *AEB* (reprend le frein si CRITICAL
persiste > 0,4 s et si le conducteur ne freine pas). Reprise conducteur par
accélération explicite. **15 tests dédiés** verrouillent chaque comportement.

**J.5 — Mini-carte radar** (`world/hud/minimap.py`). Vue top-down dans le
panneau gauche du HUD, cône de perception teinté, acteurs colorés par niveau
positionnés dans le repère ego (avant/droite). Utile en conduite libre car la
caméra ne montre pas les côtés.

**J.6 — Point d'entrée `apps/carla_freedrive.py`**. Assemble tout : formulaire
(onglet Conduite libre ajouté) → spawn ego + trafic IA → boucle synchrone
avec perception oracle → contrôle clavier → assistance → HUD enrichi + log CSV.

## Phase K — Audit du moteur

**K.1 — Correction du RSS sur sol dégradé** (D14). Le modèle RSS appliquait une
décélération garantie `b_min = 4 m/s²` **quel que soit l'état de la chaussée**.
Sur verglas (µ·g ≈ 2,9 m/s²), c'est physiquement impossible : le RSS
sous-estimait la distance de sécurité là où il fallait être le plus prudent.
Mesure avant correction : à 90 km/h sur verglas, RSS = 66 m contre 106 m de
distance d'arrêt physique. Correction : `b_min` plafonnée à µ·g. Effet : RSS
passe à 96,7 m et le niveau de SAFE à DANGER. Calibration inchangée (le jeu de
référence ne contient pas de cas verglas + suivi). Deux invariants ajoutés.

**K.2 — Suppression du code mort.** `_cap_a_composantes` dans
`risk_engine/lateral.py` et `_critique` dans `sim/visualize.py` étaient définis
mais jamais appelés.

**K.3 — Vérifications systématiques passées.** 12/12 contrôles de cohérence
physique (formules TTC/THW/DRAC recalculées à la main, plages µ·g, distances
d'arrêt), 5/5 tests de monotonie fine (balayages au pas de 1 m, 2 km/h, 0,5 m
d'écart latéral), 18/18 cas d'entrées extrêmes gérés sans NaN ni exception,
24/24 préréglages évaluables via l'API avec cohérence API/moteur vérifiée,
couverture 92 % sur `risk_engine/`.

## Phase L — Géométrie 2D du conflit (v1.8)

**L.1 — Module de géométrie partagée** (`risk_engine/geometry.py`). La
conversion (distance, écart latéral, cap) → pose 2D n'existait que dans le
simulateur, ce qui interdisait au moteur tout raisonnement géométrique. Extraite
et partagée : moteur et simulateur placent désormais les agents à l'identique.
125 tests inchangés après refactorisation, preuve d'équivalence.

**L.2 — PET géométrique 2D** (`metrics.pet_2d`). L'ancien PET renvoyait
`distance / v_ego` sans tenir compte de l'écart latéral. La nouvelle version
construit la zone de conflit, compare les créneaux d'occupation des deux usagers
et renvoie 0 en cas de recouvrement. Horizon de confiance de 4 s : au-delà,
la prédiction à vitesse constante n'est plus tenable et le PET n'est pas
renseigné.

**L.3 — Retrait du TTC hors de son domaine de validité** (D15). Le TTC est
neutralisé pour les conflits de croisement, où il mesure une grandeur sans
signification physique. N'est sûr qu'associé à L.2 : seul, il produit 4
détections manquées (mesuré et verrouillé par un test).

**L.4 — Le PET modulé par la marge contextuelle**. Devenu métrique décisive en
croisement, le PET devait subir la même contextualisation que le TTC, sans quoi
la vulnérabilité de l'usager cessait d'agir là où elle importe le plus.

**L.5 — Trois pistes mesurées puis rejetées** : plafonnement de la marge
contextuelle (globale puis limitée aux motorisés), et déclassement sur
corroboration faible. Toutes violaient la contrainte de sécurité. Ces échecs
établissent que le conservatisme du moteur est structurel, pas un défaut de
réglage — résultat exploitable au mémoire.

**Effet global** : 16/24 → **17/24 (71 %)**, fausses alarmes 8 → 7, détections
manquées 0 → 0. Suite de tests 113 → **125**.

## Phase M — Rejeu validé et double de test CARLA

**M.1 — Double de test CARLA** (`tests/fake_carla.py`). Implémente assez de
l'API CARLA (Client, World, Map, Actor, blueprints, capteurs, TrafficManager,
physique élémentaire) pour exécuter toute la chaîne d'intégration sans GPU.
Motivation : quatre erreurs d'API étaient passées en production faute de serveur
sous la main. 10 tests d'intégration verrouillent désormais les signatures.

**M.2 — Correction du rejeu.** `contexte_courant()` était appelé sans argument
alors que la signature en exigeait un : les 24 rejeux échouaient et le bilan
était vide. Corrigé, plus restauration d'une docstring détruite par une
insertion antérieure dans `appliquer_scenario`.

**M.3 — Méthodologie du rejeu revue.** Le bilan comparait une **étiquette
décrivant l'instant t = 0** au **maximum atteint sur plusieurs secondes** —
comparaison biaisée par construction, puisque l'ego roule vers le conflit et que
presque tout scénario finit CRITICAL. Le CSV expose désormais quatre colonnes :
étiquette attendue, niveau hors ligne, niveau au premier tick CARLA (seul
comparable à l'étiquette), et maximum sur la durée (informatif). Deux
indicateurs distincts en découlent : **fidélité du portage** (CARLA t0 == hors
ligne), qui valide l'intégration, et **accord avec l'étiquette**, qui mesure la
calibration.

## Phase N — Perception ouverte et recommandations

**N.1 — Écart latéral calculé depuis les poses** (D16). `agent_from_observation`
ne renseignait pas `ecart_lateral_m` : tout agent venant de CARLA était traité
comme étant dans la voie de l'ego. Cause principale des alertes intempestives en
conduite libre.

**N.2 — VRU longeant contre VRU traversant** (D16). La règle « ne jamais
rétrograder un VRU » est restreinte aux conflits de croisement. Un piéton qui
longe le trottoir ne déclenche plus d'alerte ; celui qui traverse reste détecté.

**N.3 — Capteur d'obstacle assaini** (D16). Filtrage en cinq étapes contre
l'« obstacle fantôme à 0 m » causé par la capsule du capteur traversant le sol.

**N.4 — Recommandations d'action affichées** (`risk_engine/advice.py`). Le
moteur ne dit plus seulement *où en est* la situation mais *quoi faire* :
consigne chiffrée obtenue en inversant le moteur par dichotomie, avec sa
justification physique. Affichée dans un bandeau dédié du HUD.

**N.5 — Trajet A → B, deux régimes** (`apps/carla_trajet.py`, D17). Sur route
vide, le critère est *aucune alerte* : toute alerte y est un faux positif
imputable à la perception. Avec trafic (`--vehicules`, `--pietons`), le critère
devient *zéro collision et arrivée à destination*. Mesuré : 40 véhicules et
20 piétons franchis sans collision, maximum DANGER.

**N.6 — Disponibilité CARLA vérifiée à l'appel** (D18). Les modules figeaient
la présence de `carla` au moment de l'import, ce qui les rendait définitivement
inutilisables si l'import survenait trop tôt. Détecté par deux tests qui
passaient isolément mais échouaient en suite complète.

**N.7 — Analyse de sensibilité des poids de pertinence** (D19). Perturbation
systématique des coefficients de `weighting.POIDS` sur les 24 scénarios : le
niveau et la métrique décisive ne changent jamais (confirmation de D4), et la
métrique d'impact est insensible à la valeur exacte des poids intermédiaires
(±0,2 ou aplatissement à 0,5 : aucun changement). Seule l'existence d'une
graduation sous 1 compte — la supprimer modifie 5 scénarios sur 24.

## Phase O — Voies et scenarios de trafic

**O.1 — Raisonnement par voie** (`world/lane_relation.py`, D20). Relation entre
véhicules déduite des waypoints CARLA, écart latéral et cap relatif mesurés le
long de la route. Corrige une **détection manquée** : un obstacle immobile dans
la voie de l'ego, à 40 m, était classé SAFE dès que la route tournait.

**O.2 — Quatre scenarios de trafic** (`world/traffic.py`, D21). Normal, peu
dense, dense, imprévisible. Le quatrième ajoute des écarts de conduite
contextuels, choisis parmi les candidats plausibles, à propension exprimée par
seconde, avec un générateur par véhicule.

**O.3 — Journal structuré** (`world/simulation_log.py`). Deux flux : évaluations
de risque avec leurs justifications, et écarts de conduite. Seules les lignes
informatives sont écrites.

**O.4 — Carte du double de test enrichie**. Rocade circulaire à quatre voies
avec `road_id` / `lane_id` — la courbure est ce qui met en défaut le
raisonnement euclidien, il fallait donc pouvoir la simuler.

## Phase H — Documentation

**H.1 — Documentation projet.** `README.md`, `FILES.md`, `DECISIONS.md` (10
décisions au format problème / options / choix / justification), `TESTS.md`
(protocole, résultats, couverture), `BASELINE_v1.md` (baseline figé),
`ETIQUETAGE.md` (méthode d'étiquetage), `CHANGELOG.md` (calibration et global).

**H.2 — Documents pour le mémoire.** `Correspondance_rapport_documents.md`
relie chaque section du rapport à sa ou ses sources documentaires ; les
documents autonomes (Pistes de réflexion, Métriques, Self-critiques, Journaux)
sont à jour.

---

## Ce qui reste ouvert

- **Partie II du mémoire — intégration CARLA** (adaptateur `world/` prêt, HUD à
  concevoir, ressource GPU requise).
- **Validation croisée** des seuils optimisés v1.2 avant adoption définitive.
- **Régression logistique** des poids de pondération quand le jeu atteindra
  ~50 scénarios.
- **Modélisation 2D du conflit latéral** (intersection de trajectoires, PET
  mesuré) pour attaquer les fausses alarmes structurelles restantes.
