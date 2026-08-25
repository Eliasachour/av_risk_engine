# Calibration du moteur — protocole et résultats de référence (v1)

> **Statut : point de départ (baseline) non réglé.** Ce document fige l'état du
> moteur *avant* tout ajustement de seuils ou de poids, afin de servir d'étalon aux
> calibrations futures. Configuration évaluée : `RiskConfig()` par défaut.
> Reproduire : `python3 calibrate.py` (détail par métrique : `--details`).

## 1. Objectif

La calibration **valide et mesure** le moteur ; elle ne l'optimise pas encore
automatiquement. Elle confronte les verdicts du moteur à un jeu de scénarios
étiquetés par jugement d'expert, et quantifie l'écart pour guider les réglages
ultérieurs (seuils, poids).

## 2. Protocole

**Scénario de référence.** Chaque cas associe un contexte de conduite complet à un
**niveau de risque attendu** (vérité terrain d'expert). Le niveau attendu est posé
par raisonnement, indépendamment de la sortie du moteur, pour éviter toute
circularité.

**Principe d'étiquetage.** CRITICAL si la collision est inévitable (décélération
requise supérieure à l'adhérence disponible µ·g, ou TTC < 1 s) ; DANGER si évitable
mais tendu (TTC 1–2 s, ou freinage proche de µ·g) ; WATCH si TTC 2–4 s ; SAFE
au-delà. Les conditions dégradées abaissent µ·g : une situation modeste peut
basculer d'un cran.

**Couverture.** 24 scénarios (SC-01 à SC-24) répartis sur trois axes : les familles
de conflit (suivi, croisement, face-à-face), les quatre niveaux, et les conditions
(sec, mouillé, verglas, neige, brouillard, nuit). Chaque famille est représentée à
plusieurs niveaux ; les traversées de VRU exploitent l'écart latéral de départ.

**Métriques d'évaluation.** Matrice de confusion (attendu × prédit) et **coût
asymétrique** : une *détection manquée* (sous-classement, prédit < attendu) est bien
plus grave qu'une *fausse alarme* (surclassement). On rapporte séparément :
détections manquées (critère de sécurité prioritaire), fausses alarmes, exactitude.

## 3. Résultats de référence

Exactitude **13/24 (54 %)** · détections manquées **0** · fausses alarmes **11**.

Matrice de confusion (lignes = attendu, colonnes = prédit) :

```
            SAFE  WATCH  DANGER  CRITICAL
  SAFE        3     2      0       0
  WATCH       0     0      2       0
  DANGER      0     0      4       7
  CRITICAL    0     0      0       6
```

La diagonale (13 cas) est correcte ; tout ce qui est au-dessus d'elle est une fausse
alarme (surclassement) ; il n'y a **rien en dessous** (aucune détection manquée).

## 4. Interprétation

**La sécurité tient largement.** Zéro détection manquée sur 24 scénarios variés, y
compris verglas, brouillard, nuit et traversées de piétons : la garantie
conservatrice du « pire niveau » se confirme bien au-delà des six cas initiaux.

**Un biais systématiquement conservateur.** Le moteur ne sous-classe jamais mais
sur-classe régulièrement (typiquement d'un cran). Ce biais est *sûr* mais coûteux en
fausses alarmes, et se concentre en trois foyers, chacun identifié par sa métrique
déclencheuse :

- **RSS et suivi normal** (ex. SC-08) : l'enveloppe RSS, très conservatrice, classe
  en DANGER un suivi qui relève humainement du WATCH (violation de la distance
  prouvée dès des écarts courants). Déclencheur : RSS.
- **TTC et traversées de VRU** (SC-12, 13, 14, 16, 21) : la marge « usager
  vulnérable » abaisse fortement le TTC effectif et escalade la plupart des
  traversées d'un niveau. Déclencheur : TTC.
- **DRAC et face-à-face à distance** (SC-17, 18) : la vitesse de fermeture frontale
  élevée déclenche le DRAC même pour un véhicule lointain resté dans sa voie, faute
  de modéliser la séparation latérale. Déclencheur : DRAC.

**Réserves de méthode.** Les niveaux attendus sont des jugements d'expert : certaines
fausses alarmes peuvent tenir à l'étiquette autant qu'au moteur, et devront être
revues. Les foyers restants renvoient à des limites déjà identifiées (conservatisme
du RSS, absence de conflit latéral 2D).

## 5. Rôle de ce point de départ

Ce baseline est **figé et daté** : il sert d'étalon. Toute calibration future (réglage
de seuils, apprentissage des poids par régression logistique) sera mesurée contre
lui — l'objectif étant de **réduire les fausses alarmes sans jamais faire apparaître
de détection manquée**. Chaque itération devra consigner : la modification apportée,
sa justification, et son effet sur les trois compteurs.

## 6. Traçabilité

- Scénarios et niveaux attendus (avec justifications) : `calibration/scenarios_ref.py`.
- Logique d'évaluation : `calibration/evaluate.py`.
- Configuration évaluée : `RiskConfig()` par défaut (`risk_engine/engine.py`).
- Commande de reproduction : `python3 calibrate.py`.
