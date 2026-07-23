# Tests — stratégie, résultats et couverture

> **Règle d'or : ces résultats se *génèrent*, ils ne s'écrivent pas à la main.**
> La liste des tests, le compteur et la couverture sont produits par `pytest` ;
> les recopier à la main revient à en oublier. On régénère à chaque évolution.

## Comment lancer

```bash
python3 -m pytest -q                       # exécution rapide (compteur)
python3 -m pytest -v                        # liste exhaustive, un test par ligne
python3 -m pytest --cov=risk_engine --cov=sim --cov=world \
                  --cov=calibration --cov=scenarios --cov-report=term-missing
```

## Résultat courant

**77 tests, 100 % au vert.** Couverture globale 56 % — mais cette moyenne mélange
le cœur logique (très couvert) et les couches d'interface/rendu (non testables sans
environnement graphique), qu'il faut lire séparément :

| Module                     | Couverture | Nature |
|----------------------------|-----------:|--------|
| `risk_engine/engine.py`    | 96 % | cœur — décision |
| `risk_engine/metrics.py`   | 93 % | cœur — métriques |
| `risk_engine/modifiers.py` | 98 % | cœur — contextualisation |
| `risk_engine/weighting.py` | 95 % | cœur — pondération |
| `risk_engine/sanitize.py`  | 98 % | cœur — robustesse |
| `risk_engine/context.py`   | 95 % | cœur — structures |
| `world/extraction.py`      | 100 % | géométrie |
| `sim/kinematic.py`         | 100 % | simulateur |
| `scenarios/constraints.py` | 95 % | cohérence de saisie |
| `calibration/`             | 63–100 % | validation |
| `scenarios/form.py`        | 0 % | **GUI tkinter** — nécessite un écran |
| `sim/visualize.py`         | 0 % | **rendu matplotlib** — nécessite un écran |
| `world/carla_world.py`     | 0 % | **glu CARLA** — nécessite CARLA + GPU |

La logique de risque (le calcul et la décision) est donc exercée à **~93–100 %** ;
les 0 % concernent uniquement l'affichage, l'interface et l'intégration CARLA, qui
relèvent d'entrées/sorties dépendantes de l'environnement, pas de l'algorithme.

## Ce que valide chaque fichier de test (l'intention)

- **test_metrics.py** (18) — les six métriques et leurs cas limites : TTC (suivi,
  croisement, face-à-face, non-approche), TTC à accélération constante (garde
  d'arrêt, freinage/accélération du lead), THW, DRAC, distance de freinage, distance
  RSS, PET (croisement vs indéfini), CI (borné, croissant).
- **test_engine.py** (7) — la décision : SAFE lointain, CRITICAL proche, SC-02,
  escalade par friction, prudence accrue pour usager vulnérable, pire cas
  multi-agents, effet de l'incertitude de profondeur.
- **test_thresholds.py** (6) — la grille : classement des six métriques, niveau
  global = pire, DRAC « impossible » fixe vs µ·g, RSS neutralisé hors suivi, RSS
  binaire, seuils configurables.
- **test_weighting.py** (4) — pondération : criticité bornée [0,1], PET non pertinent
  en suivi, classement décroissant, impact et corroboration exposés.
- **test_sanitize.py** (5) — robustesse : bornage vitesse/accélération, repli du cap,
  remplacement des NaN, valeurs valides inchangées.
- **test_kinematic.py** (7) — simulateur : escalade sans réaction, évitement avec
  réaction, freinage plafonné à µ·g, traversée par écart latéral, arrêt complet
  d'un obstacle en voie.
- **test_extraction.py** (6) — géométrie : distance plane, cap (même sens, face-à-face,
  croisement, repli autour de 360°), reconstruction du contexte.
- **test_constraints.py** (9) — cohérence de saisie : météo ↔ état de route, visibilité
  de nuit, limites selon le type de route et zone de travaux, plausibilité.
- **test_report.py** (5) — présentation : une ligne par agent, métriques complètes,
  formatage, cas sans agent.
- **test_weather.py** (4) — conversion météo CARLA.
- **test_calibration.py** (5) — jeu de référence fourni, somme de la matrice,
  synthèse cohérente, ancres non ambiguës, **zéro détection manquée**.
- **test_optimize.py** (1) — l'optimiseur ne crée jamais de détection manquée et ne
  régresse pas sur les fausses alarmes.

## Principe de reproductibilité

Chaque évolution du code doit laisser la suite au vert. Un test qui casse signale
soit une régression, soit une décision de calibration à consigner (voir
`calibration/CHANGELOG.md`). On ne « rend pas un test vert » en l'affaiblissant sans
justification écrite.
