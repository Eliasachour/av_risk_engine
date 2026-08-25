# Référentiel d'étiquetage des scénarios de calibration

Ce document définit **la méthode par laquelle chaque scénario de référence reçoit
son niveau attendu** (SAFE / WATCH / DANGER / CRITICAL). L'étiquetage est une
*vérité terrain* : c'est ce à quoi la sortie du moteur est comparée pour mesurer
son erreur. Il doit donc être posé indépendamment du moteur, de manière rigoureuse
et reproductible.

**Principe directeur.** L'étiquetage suit une règle **physique** en trois étapes,
appliquées dans l'ordre. Chaque étape ne se déclenche que si la précédente n'a pas
conclu. Le résultat est reproductible : quiconque applique la méthode aux mêmes
paramètres obtient la même étiquette.

**En cas de doute résiduel**, on penche vers le niveau **le plus sévère** — un
sur-classement (fausse alarme) coûte moins qu'un sous-classement (détection manquée),
car ce dernier violerait la contrainte de sécurité prioritaire.

## Étape 1 — Test d'inévitabilité (la physique tranche)

On calcule la **décélération requise** pour éviter la collision, à partir de la
vitesse de fermeture et de la distance :

`a_requis = v_fermeture² / (2 · d)`

où `v_fermeture = v_ego + v_agent · cos(cap)` (approximation longitudinale) et
`d` est la distance à l'agent.

On la compare à l'**adhérence disponible** `µ · g` selon l'état de la route :

| État de la route | µ    | µ · g (m/s²) |
|------------------|-----:|-------------:|
| sec              | 0,90 | 8,8          |
| mouillé          | 0,64 | 6,3          |
| neigeux          | 0,50 | 4,9          |
| verglas          | 0,30 | 2,9          |

**Règle 1.** Si `a_requis > µ · g` → collision **inévitable** → **CRITICAL**. On
s'arrête ici : la physique ne laisse aucun degré de liberté.

Sinon, on passe à l'étape 2.

## Étape 2 — Graduation par le TTC (situation évitable)

Quand la collision est physiquement évitable, on gradue par le **temps avant
collision** :

`TTC = d / v_fermeture`

On applique la grille conventionnelle des études de conflits (Hayward, 1972 ; seuil
critique le plus cité à 1,5 s ; identique aux seuils par défaut de `RiskConfig`) :

| TTC        | Niveau   | Interprétation                              |
|------------|----------|---------------------------------------------|
| > 4 s      | SAFE     | aucune menace immédiate                     |
| 2 à 4 s    | WATCH    | vigilance, marge confortable                |
| 1 à 2 s    | DANGER   | évitable mais freinage fort requis          |
| < 1 s      | CRITICAL | temps de réaction humain dépassé            |

**Règle 2.** Retenir le niveau correspondant à la plage du TTC.

## Étape 3 — Durcissement contextuel (un cran, en zone temporelle tendue)

Certains contextes justifient une prudence supplémentaire, mais on limite le
durcissement à **un seul cran au total**, quel que soit le nombre de facteurs
défavorables — cela évite toute escalade arbitraire.

**Principe.** Le durcissement contextuel a pour but de compenser des marges
d'incertitude qu'on ne peut pas mesurer directement (fragilité corporelle du piéton,
distance de freinage plus grande sur sol glissant, perception dégradée la nuit).
Cette prudence n'est utile que quand un conflit se profile à un horizon proche :
un usager vu très loin n'exige pas encore d'alerte. Un piéton perçu à 5 secondes
laisse largement le temps de réagir ; un piéton à 1 seconde ne pardonne aucune
imprécision.

**Deux préalables cumulatifs pour appliquer le durcissement :**

1. **Un conflit existe.** Si l'agent s'éloigne (`v_fermeture ≤ 0`) ou si le TTC
   est infini, aucun durcissement — l'étiquette reste SAFE quelle que soit la météo.
2. **Le conflit est déjà tendu.** Le niveau de base issu de l'étape 2 est déjà
   ≥ WATCH *et* le TTC longitudinal est inférieur à 2 s. Ce seuil de 2 s
   correspond à la frontière WATCH/DANGER : au-dessus, l'ego a le temps de
   réagir sans alerte supplémentaire ; en dessous, la marge se resserre et la
   prudence est justifiée.

**Règle 3.** Si les deux préalables sont vérifiés, durcir d'**un cran** si au moins
l'une des trois conditions est vraie :

- **Usager vulnérable** — l'agent le plus critique est un piéton, un cycliste, ou
  un ouvrier.
- **Sol dégradé** — état de route mouillé, neigeux ou verglas (indépendamment de
  l'étape 1, où le µ · g réduit était déjà utilisé).
- **Visibilité dégradée** — nuit, brouillard, ou visibilité inférieure à 100 m.

Si plusieurs conditions sont vraies, on durcit tout de même d'un seul cran. Le
niveau ne peut jamais dépasser CRITICAL.

**Ce que ce raffinement évite.** Sans le préalable de tension temporelle, un
piéton qui traverse à 40 m d'écart 6 m — TTC longitudinal ≈ 2,9 s, zone WATCH —
serait automatiquement durci en DANGER par la seule présence de vulnérabilité. Or
l'ego a près de 3 secondes pour réagir : c'est confortable. Alerter au niveau
DANGER un usager encore lointain revient à saturer l'échelle, ce qui *dégrade*
la sécurité en la banalisant. On concentre le durcissement là où il compte.

## Étape 4 — Correction géométrique latérale (agent hors trajectoire)

La méthode des étapes 1 à 3 est purement **longitudinale** : elle ignore la
position latérale de l'agent. Elle sur-évaluerait donc un agent qui traverse loin
sur le côté d'une route large. On ajoute une correction :

**Règle 4.** Si l'agent est franchement **hors de la trajectoire de collision** —
concrètement, si son écart latéral courant *et* projeté à l'horizon TTC dépassent
tous deux deux fois la largeur d'une voie (≈ 7 m) —, on **annule le durcissement
contextuel appliqué à l'étape 3** : l'étiquette redescend au niveau qu'elle avait
avant durcissement.

Sécurité : on ne « rétrograde » que ce que l'étape 3 avait ajouté, jamais ce que
l'étape 1 (physique) ou l'étape 2 (TTC longitudinal) ont établi. Un CRITICAL par
inévitabilité reste CRITICAL même si l'agent est latéralement décalé. Un DANGER
par TTC sub-secondaire reste DANGER.

## Récapitulatif — comment étiqueter un nouveau scénario

1. Calculer `v_fermeture`, puis `a_requis = v_fermeture² / (2 · d)`.
2. Comparer à `µ · g` : si `a_requis > µ · g`, étiquette = **CRITICAL**, terminé.
3. Sinon, calculer `TTC = d / v_fermeture` et lire l'étiquette (le *niveau de base*)
   dans la grille TTC.
4. Si un conflit existe (`v_fermeture > 0`), *si le niveau de base est ≥ WATCH*,
   *et si TTC < 2 s* : vérifier les trois conditions de contexte (VRU, sol dégradé,
   visibilité dégradée). Si l'une est vraie, durcir d'un cran.
5. Si l'agent est franchement hors trajectoire de collision (écart latéral courant
   *et* projeté à l'horizon TTC tous deux > ~7 m), annuler le durcissement de
   l'étape 4 (revenir au niveau d'avant durcissement).
6. En cas de doute résiduel (valeurs à la limite d'une plage), choisir le niveau
   plus sévère.

## Exemples travaillés

### Exemple A — Suivi à distance moyenne
- Contexte : ego 90 km/h sur nationale sèche, agent voiture 80 km/h à 40 m, cap 0°.
- Étape 1 : `v_ferm = 2,8 m/s` ; `a_requis = 2,8² / (2·40) ≈ 0,1 m/s²` ≪ 8,8. Évitable.
- Étape 2 : `TTC = 40 / 2,8 ≈ 14 s` > 4 s → **SAFE**.
- Étape 3 : aucune condition défavorable → pas de durcissement.
- **Étiquette : SAFE.**

### Exemple B — Suivi serré à haute vitesse
- Contexte : ego 110 km/h sur autoroute sèche, agent 80 km/h à 15 m, cap 0°.
- Étape 1 : `v_ferm = 8,3 m/s` ; `a_requis = 8,3² / (2·15) ≈ 2,3 m/s²` < 8,8. Évitable.
- Étape 2 : `TTC = 15 / 8,3 ≈ 1,8 s` → **DANGER**.
- Étape 3 : rien à durcir.
- **Étiquette : DANGER.**

### Exemple C — Obstacle immobile sur verglas
- Contexte : ego 70 km/h, agent voiture 0 km/h à 50 m, cap 0°, verglas.
- Étape 1 : `v_ferm ≈ 19,4 m/s` ; `a_requis = 19,4² / (2·50) ≈ 3,8 m/s²`. Sur
  **verglas**, `µ · g = 2,9 m/s²`. Or `3,8 > 2,9` → **inévitable** → **CRITICAL**.
- **Étiquette : CRITICAL** (Règle 1 s'applique).

### Exemple D — Ouvrier en zone de travaux
- Contexte : ego 30 km/h dans une zone de travaux, ouvrier à 12 m, cap 45°, sec.
- Étape 1 : `v_ferm ≈ 8,3 m/s` (ouvrier quasi statique) ; `a_requis = 8,3² / (2·12) ≈ 2,9 m/s²` ≪ 8,8. Évitable.
- Étape 2 : `TTC = 12 / 8,3 ≈ 1,4 s` → **DANGER**.
- Étape 3 : ouvrier = usager vulnérable → **+1 cran** → **CRITICAL**.
- **Étiquette : CRITICAL.**

## Limites assumées de la méthode

**La méthode ne modélise pas certains phénomènes** qui, dans la réalité, aggravent
la situation : la trajectoire des VRU en 2D (un piéton qui va traverser vs qui reste
sur le trottoir), les zones de conflit géométriques (angles morts, virages sans
visibilité), et la contrainte imposée par les règles de circulation (zone de travaux,
limitation de vitesse locale). Ces cas se traduisent par des étiquettes potentiellement
imparfaites — c'est la matière de la self-critique du moteur.

**Cas particulier — la méthode diverge parfois du modèle RSS.** Le RSS (Shalev-Shwartz)
définit une distance de sécurité *prouvée* qui, à haute vitesse et pour un temps de
réaction usuel, peut être bien supérieure au seuil du TTC. Un suivi à 40 m à 90 km/h
donne TTC ≈ 14 s → SAFE par la méthode, alors que la distance RSS n'est pas respectée.
On retient l'étiquette de la méthode (SAFE), plus proche de la perception humaine et
défendable par une règle reproductible, tout en documentant l'écart : le RSS
demeure un modèle plus conservateur, utile comme *drapeau* (indication d'une marge
sous la sécurité prouvée) mais non retenu comme critère d'étiquetage.

**En pratique, la méthode donne parfois des résultats contre-intuitifs.** Un suivi
que le conducteur trouverait « normal » peut être étiqueté SAFE par la physique
alors qu'un modèle très conservateur (le RSS) considère la distance de sécurité
comme violée. On garde alors l'étiquette physique — c'est elle qu'on peut défendre
comme reproductible et fondée.
