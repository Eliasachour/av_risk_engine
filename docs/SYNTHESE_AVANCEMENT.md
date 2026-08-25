# Synthèse de l'avancement — av_risk_engine

Document de synthèse retraçant l'ensemble du travail, de la conception initiale
à l'état courant. Il agrège les journaux détaillés (`docs/CHANGELOG.md`,
`calibration/CHANGELOG.md`, `docs/DECISIONS.md`) en une lecture continue,
destinée à servir de fil directeur pour la rédaction du mémoire.

**État au 17 août 2026** — 161 tests · 0 détection manquée · 7 fausses alarmes ·
17/24 (71 %) d'exactitude · 15 décisions techniques documentées.

---

## 1. Vue d'ensemble en une page

| | |
|---|---|
| **Objet** | Moteur d'évaluation du risque pour véhicule autonome, multi-métriques et contextualisé |
| **Métriques** | TTC, THW, PET, RSS, CI, DRAC — agrégées par le pire niveau |
| **Niveaux** | SAFE · WATCH · DANGER · CRITICAL |
| **Contextualisation** | adhérence µ·g, visibilité, vulnérabilité de l'usager, incertitude de mesure |
| **Interfaces** | console · formulaire tkinter · web (React + FastAPI, déployé) · CARLA (HUD Pygame) |
| **Validation** | 24 scénarios de référence · 161 tests dont 14 invariants physiques · rejeu CARLA des 24 scénarios |
| **Traçabilité** | 15 décisions au format problème/options/choix/justification · 11 versions de calibration |

**Ce qui distingue ce travail.** Le moteur est déterministe et explicable par
construction : chaque verdict est justifiable par une mesure physique. Il se
positionne en aval des chaînes de perception (BEVFormer, UniAD…) plutôt qu'en
concurrence avec elles, et sa contribution est la **traçabilité** de
l'évaluation, non la performance de la perception.

---

## 2. Chronologie du développement

### Phase A — Le moteur (conception initiale)

Grille de décision à quatre niveaux fondée sur le pire des six métriques, avec
traçage de la métrique déclencheuse. Contextualisation appliquée au TTC seul,
pour éviter le double comptage sur des métriques déjà physiques. Freinage
plafonné à l'adhérence µ·g. Briques de pondération (explicabilité) et
d'assainissement (robustesse des entrées).

*Décisions structurantes : découplage du moteur de son environnement (D1, D9).*

### Phase B — Le simulateur cinématique

Simulateur 2D indépendant de CARLA, permettant de développer et de tester sans
GPU. Écart latéral câblé de bout en bout (le champ existait mais n'était pas
transmis). Vue de dessus multi-agents. Freinage d'urgence différencié, puis
fondé sur la physique : décélération réellement requise plafonnée à µ·g, avec
diagnostic explicite évitable / inévitable.

*Décision : freinage physique et diagnostic de collision (D7).*

### Phase C — Décision géométrique

Filtrage latéral 2D : facteur de menace fondé sur l'écart latéral projeté à
l'horizon TTC, en atténuation seulement — un agent hors trajectoire peut être
rétrogradé, jamais aggravé. Règle asymétrique préservant les usagers
vulnérables.

*Décision : filtrage latéral (D8).*

### Phase D — Calibration et étiquetage

Jeu de référence porté de 6 à 24 scénarios, couvrant trois familles de conflit,
quatre niveaux et des conditions dégradées. Baseline figé et documenté.
Optimiseur de seuils par descente par coordonnées sous contrainte dure
« zéro détection manquée » — le résultat reste une **proposition non adoptée**,
faute de validation croisée.

Surtout : un **référentiel d'étiquetage reproductible** en quatre règles
physiques ordonnées (inévitabilité, graduation TTC, durcissement contextuel en
zone tendue, correction géométrique latérale). Chaque étiquette devient
défendable par le calcul.

*Épisode central : le demi-tour v1.6 → v1.7. Un durcissement méthodique de la
règle 3 a introduit 3 détections manquées — inacceptable. La règle a été
amendée pour ne durcir qu'en zone temporelle tendue. Cet aller-retour est
documenté tel quel : trop de rigueur peut casser la contrainte de sécurité.*

### Phase E — Robustesse et invariants

Passage d'un baseline *déclaré* à un baseline *garanti*. Douze propriétés
physiques verrouillées automatiquement — monotonie en distance, sévérité accrue
sur sol dégradé / de nuit / pour un VRU / en profondeur inférée, niveau global
égal au pire agent, filtrage latéral jamais amplifiant, agent qui s'éloigne =
SAFE, NaN toléré, obstacle inévitable = CRITICAL. Une régression future se voit
immédiatement au lieu d'attendre la calibration suivante.

### Phase F — Interface web

API FastAPI exposant le moteur (huit endpoints), frontend React + Vite +
TypeScript. Tableau de bord à trois panneaux : scénario avec préréglages,
évaluation en temps réel, simulation animée et graphes agrandissables.

Point de conception notable : les règles de cohérence entre paramètres (météo ↔
état de route, visibilité plausible, limites par type de route) restent dans
`scenarios/constraints.py` et sont **servies** par un endpoint dédié. Source
unique de vérité, appliquée automatiquement dans le formulaire et vérifiée côté
serveur.

*Décision : interface web découplée (D10). Troisième interface du même moteur,
sans duplication de logique — la démonstration concrète du découplage.*

### Phase G — Déploiement

Backend et frontend déployés sur Render. Détection d'environnement dans le
client (proxy en développement, URL de production au build).

### Phase I — Préparation de l'intégration CARLA

Extraction de la logique de commande dans un module pur du moteur, avec sortie
normalisée en `throttle` / `brake` ∈ [0,1] directement consommable par
`carla.VehicleControl`. Le simulateur interne et la glu CARLA consomment la même
fonction.

*Décision : commande recommandée exportable (D11). Le champ `steer` n'est
volontairement pas exposé — le moteur ne modélise pas la trajectoire latérale.*

### Phase J — Intégration CARLA

Pont de perception (mode synchrone 20 Hz), HUD Pygame, boucle de contrôle
automatique, rejouabilité des 24 scénarios de référence pour comparer prédiction
et comportement observé.

Puis le **mode conduite libre** : trafic autonome (véhicules du Traffic Manager,
piétons IA), conduite au clavier, et le moteur en observation avec trois niveaux
d'assistance — évaluation seule, alerte visuelle, freinage d'urgence automatique
sur CRITICAL persistant.

*Décisions : architecture d'intégration (D12), perception oracle assumée et
assistance graduée (D13).*

### Phase K — Audit du moteur

Audit systématique en fin de développement, qui a révélé **une erreur de
modélisation** : le RSS appliquait une décélération garantie de 4 m/s² quel que
soit l'état de la chaussée. Sur verglas (µ·g ≈ 2,9 m/s²), c'est physiquement
impossible — le RSS sous-estimait la distance de sécurité exactement là où il
fallait être le plus prudent. Mesure avant correction : à 90 km/h sur verglas,
RSS = 66 m contre 106 m de distance d'arrêt réelle.

*Décision : décélération RSS plafonnée à l'adhérence disponible (D14). Effet :
RSS passe à 96,7 m et le niveau de SAFE à DANGER.*

Également vérifiés à cette occasion : 12 contrôles de cohérence physique
(formules recalculées à la main), 5 tests de monotonie fine par balayage,
18 cas d'entrées extrêmes, cohérence API/moteur sur les 24 préréglages,
92 % de couverture sur le cœur.

### Phase L — Géométrie 2D du conflit

Traitement de la dernière limite structurelle identifiée. Voir section 4 pour le
détail, cette phase méritant un exposé complet de la démarche.

---

## 3. Les quinze décisions techniques

| # | Décision | Enjeu |
|---|---|---|
| D1 | Grille multi-métriques à quatre niveaux | non sous-estimation par construction |
| D2 | Contextualisation via le TTC effectif | éviter le double comptage |
| D3 | Freinage plafonné à µ·g | cohérence physique |
| D4 | Métriques au bon niveau de fidélité | RSS binaire, TTC à accélération constante |
| D5 | Brique de pondération | explicabilité sans toucher à la décision |
| D6 | Brique d'assainissement | ne jamais bloquer sur une entrée aberrante |
| D7 | Freinage physique et diagnostic de collision | évitable / inévitable explicite |
| D8 | Filtrage latéral 2D | atténuation seulement, jamais d'amplification |
| D9 | Découplage moteur / environnement | portabilité vers CARLA et le web |
| D10 | Interface web, cohérence servie par l'API | source unique de vérité |
| D11 | Commande recommandée exportable | pas de duplication simulateur / CARLA |
| D12 | Architecture d'intégration CARLA | le moteur ignore CARLA |
| D13 | Perception oracle assumée, assistance graduée | transparence sur la source de vérité |
| D14 | Décélération RSS plafonnée à µ·g | correction d'une erreur de modélisation |
| D15 | PET géométrique 2D et retrait du TTC hors domaine | chaque métrique dans son domaine |

---

## 4. Phase L en détail — une démarche exemplaire à raconter

Cette dernière phase illustre mieux que les autres la méthode suivie, et mérite
d'être exposée en détail au mémoire.

### Le point de départ

Le moteur paraissait « machinal » : un obstacle dans les environs, un verdict
sévère. Les 8 fausses alarmes de la v1.7 semblaient confirmer un excès de
conservatisme. La question posée était : faut-il de l'intelligence artificielle
pour mieux lire le contexte ?

### L'analyse préalable

Décomposition des 8 écarts, qui se révèlent de deux natures :

- **5 conflits longitudinaux** — aucune méconnaissance du contexte. Le
  sur-classement vient des paramètres RSS et de la marge contextuelle.
- **3 piétons traversants** — la métrique décisive est le **TTC**, appliqué à
  une géométrie de croisement où il ne mesure rien de physique.

Conclusion : l'IA n'aurait réglé que 3 cas sur 8, et au prix de la traçabilité
qui fait la valeur du travail.

### Trois pistes mesurées puis rejetées

| Piste | Effet mesuré | Verdict |
|---|---|---|
| Plafonner la marge contextuelle | 1 détection manquée dès ×2,0 | rejetée |
| La plafonner pour les motorisés seuls | 2 détections manquées | rejetée |
| Déclasser si une seule métrique déclenche | 8 des 13 vrais positifs concernés | rejetée |

Ces échecs ne sont pas des impasses : ils **établissent un résultat**. La marge
contextuelle est un scalaire unique qui doit couvrir friction, vulnérabilité,
visibilité et incertitude. Elle est correctement calibrée pour les pires cas —
piéton de nuit à 25 m de visibilité, facteur ×4,88 — et par construction
excessive pour les cas doux. **Les fausses alarmes sont le prix payé pour les
vraies détections.** Le conservatisme est structurel, pas un défaut de réglage.

### Le changement retenu, et ses surprises

Trois modifications indissociables :

1. **PET géométrique 2D.** L'ancien PET renvoyait `distance / v_ego` sans tenir
   compte de l'écart latéral : un piéton à 10 m sur le côté avait le même PET
   qu'un piéton dans la voie. La nouvelle version construit la zone de conflit
   et compare les créneaux d'occupation.
2. **Horizon de confiance de 4 s.** Prédire qu'un piéton entrera dans la voie
   dans six secondes suppose une vitesse constante pendant six secondes : cela
   relève de l'intention, pas de la cinématique. Le moteur préfère ne rien
   affirmer plutôt qu'affirmer faux.
3. **Retrait du TTC pour les croisements**, où il est hors de son domaine de
   validité.

Trois surprises en cours de route, toutes instructives :

- **Le PET 2D seul n'apporte rien** (écart total 10 contre 9). Le PET n'était
  pas la métrique décisive de ces cas — l'information était dans l'analyse
  initiale, elle avait été mal lue.
- **Le retrait du TTC seul produit 4 détections manquées.** On ne peut retirer
  une métrique d'un régime que si une autre, valide, y prend le relais. Les deux
  changements sont indissociables, et un test le documente désormais.
- **Un invariant a dû être révisé.** `test_vru_plus_conservateur` exigeait qu'un
  piéton obtienne un niveau *strictement* supérieur à une voiture en géométrie
  identique. Ce n'est pas un invariant valide : avec des métriques en bandes,
  aucune modulation monotone ne garantit un franchissement de bande. Le test
  assertait un effet de bord de l'ancienne géométrie. Il vérifie désormais, plus
  fortement, que la marge et la métrique effective sont strictement plus
  sévères.

Un dernier point notable : le PET 2D n'est **pas monotone** en écart latéral, et
c'est correct. Pour un ego à 50 km/h et un piéton à 30 m traversant à 5 km/h, le
PET vaut 5,22 s à 12 m d'écart, 2,26 s à 8 m, 0,00 s à 4 m, puis remonte à
0,07 s à 1 m. Le minimum est à un écart intermédiaire : à 1 m le piéton a presque
fini de traverser quand l'ego arrive. Le PET mesure une **coïncidence
temporelle**, pas une proximité — ce que l'ancienne estimation était incapable
d'exprimer.

### Effet mesuré

Exactitude **16/24 → 17/24 (71 %)** · fausses alarmes **8 → 7** · détections
manquées **0 → 0** · suite de tests **113 → 125**. SC-12 (piéton commençant à
traverser à 10 m de la voie, ego à 80 m) passe de WATCH à SAFE.

Aucune étiquette n'a été révisée pour faire converger le résultat.

---

## 5. État courant et limites assumées

### Chiffres

| Indicateur | Valeur |
|---|---|
| Tests | 135, tous verts |
| Invariants physiques verrouillés | 14 |
| Scénarios de référence | 24 |
| Détections manquées | **0** |
| Fausses alarmes | 7 |
| Exactitude | 17/24 (71 %) |
| Couverture du cœur | 92 % |
| Décisions documentées | 15 |
| Versions de calibration | 11 (v0.1 → v1.8) |

### Les sept écarts restants

Tous des fausses alarmes, aucune détection manquée. Six relèvent du compromis
structurel décrit en section 4. SC-13 (piéton à 6 m, attendu WATCH, prédit
CRITICAL) est le seul cas où le PET 2D est plus sévère que l'étiquette, la
coïncidence temporelle y étant réelle — il pose la question de la justesse de
l'étiquette autant que celle du moteur.

### Limites assumées

- **La prédiction d'intention est hors périmètre.** Le PET 2D suppose des
  trajectoires rectilignes à vitesse constante sur son horizon. Un piéton qui
  hésite, regarde, ou accélère n'est pas modélisé. C'est la limite que l'IA
  adresserait — en amont de la décision, jamais à sa place.
- **La perception n'est pas développée.** En conduite libre, le moteur reçoit la
  vérité terrain CARLA filtrée par distance et cône de vision. Le HUD l'affiche
  explicitement (« perception : oracle »).
- **Les paramètres RSS** `rho`, `a_accel` et `b_max` restent des choix de
  conception issus de la littérature, pas des mesures.
- **Le jeu de calibration compte 24 scénarios.** La validation croisée des
  seuils optimisés n'a pas été conduite, faute d'un jeu assez large.
- **L'adhérence simulée dans CARLA est approchée.** Le paramètre
  `tire_friction` n'est pas le µ physique ; on applique un ratio par rapport au
  défaut. La hiérarchie entre états est respectée, la valeur absolue est une
  approximation.
- **Le feu tricolore est détecté mais n'entre pas dans le calcul du risque.**

### Perspectives, par maturité croissante

1. Validation croisée des seuils optimisés, une fois le jeu élargi.
2. Régression logistique des poids de pondération (~50 scénarios nécessaires).
3. Intégration du franchissement de feu comme type de conflit.
4. Prédiction d'intention en amont du moteur (heuristiques, puis apprentissage).
5. Chaîne de perception réelle par capteurs, en remplacement de l'oracle.

---

## 6. Où trouver quoi

| Besoin | Document |
|---|---|
| Démarrage, arborescence | `README.md` |
| Rôle de chaque fichier | `docs/FILES.md` |
| Historique projet par phases | `docs/CHANGELOG.md` |
| Historique de calibration versionné | `calibration/CHANGELOG.md` |
| Les 15 décisions argumentées | `docs/DECISIONS.md` |
| Protocole et détail des 161 tests | `docs/TESTS.md` |
| Méthode d'étiquetage | `calibration/ETIQUETAGE.md` |
| Baseline figé | `calibration/BASELINE_v1.md` |
| Lancement CARLA | `docs/CARLA_DEMARRAGE.md` |
| Correspondance avec le mémoire | `Correspondance_rapport_documents.md` |

### Reproduire les chiffres

```bash
python3 -m pytest -q          # 161 tests
python3 apps/calibrate.py     # 17/24, 0 manquée, 7 fausses alarmes
python3 apps/optimize.py      # proposition d'optimisation (non adoptée)
```
