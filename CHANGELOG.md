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

**D.3 — Optimiseur de seuils sous contrainte** (`optimize.py`). Descente par
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

**F.1 — API FastAPI** (`api.py`). Sept endpoints : `/enums`, `/presets`,
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
