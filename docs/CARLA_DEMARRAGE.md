# Démarrage CARLA — Guide complet

Ce guide couvre les trois usages de l'intégration CARLA :
lancement d'une session interactive avec HUD, rejeu d'un scénario de référence,
et rejeu en batch de tous les 24 scénarios.

## Prérequis

**CARLA 0.9.15** installé et démarrable (sous Linux : `./CarlaUE4.sh`).

**Paquets Python** — sur la machine où tourne le client :
```bash
python3 -m pip install pygame numpy
# Le wheel CARLA (a adapter selon ta version Python)
python3 -m pip install <CARLA>/PythonAPI/carla/dist/carla-0.9.15-cp310-cp310-linux_x86_64.whl
```

## Usage 1 — Session interactive (`apps/carla_run.py`)

**Terminal 1** — serveur CARLA :
```bash
cd <CARLA>
./CarlaUE4.sh -quality-level=Low -RenderOffScreen
```

**Terminal 2** — client :
```bash
python3 apps/carla_run.py
```

Un formulaire tkinter s'ouvre en 3 onglets :
- **CARLA** : hôte/port, carte, tick rate.
- **Scénario** : préréglage SC-XX (facultatif) ou config manuelle.
- **Contrôle** : durée max, log CSV, activation de la réaction (l'ego pilote).

Clique **Lancer sur CARLA**. Le formulaire se ferme, le HUD Pygame s'ouvre.

### Le HUD

- **Bandeau supérieur** coloré selon le niveau : niveau, vitesse ego + cible,
  mode de contrôle (nominal / proportionnel / physique / pause), temps sim.
- **Panneau gauche** : liste des agents détectés, triée par criticité (max 5).
- **Zone centrale** : vue caméra RGB de l'ego.
- **Panneau droit** : jauges physiques pour l'agent le plus critique
  (TTC, THW, DRAC vs µ·g, vitesse ego vs cible), avec seuils colorés.
- **Bandeau inférieur** : diagnostic ; devient rouge pulsant en CRITICAL.

Raccourcis : **ESC** quitte, **ESPACE** met en pause (l'ego reste freiné).

### Contrôle automatique (étape 2)

Quand *"L'ego réagit"* est activé, le moteur pilote automatiquement :
- Freinage physique via `commande_recommandee` du moteur (throttle/brake ∈ [0,1]).
- Reprise ACC : quand SAFE, l'ego réaccélère vers `min(vitesse_cible, limite)`.
- Pilotage latéral simple : suivi de voie via waypoint CARLA.

Modes affichés dans le bandeau supérieur :
- **NOMINAL** : aucune action, l'ego est en croisière.
- **PROPORTIONNEL** : freinage doux selon le niveau (croisement, agent hors voie).
- **PHYSIQUE** : freinage sur décélération réellement requise (agent en voie).
- **PAUSE** : ego bloqué (frein plein).

## Usage 2 — Rejouer un scénario de référence (`apps/carla_replay.py`)

Rejoue un scénario SC-XX à l'identique dans CARLA et compare le niveau
observé avec la prédiction du moteur (calibration hors ligne).

```bash
python3 apps/carla_replay.py --preset SC-05 --duree 15
```

Un bilan est écrit dans `logs/rejeu_YYYYMMDD_HHMMSS.csv` avec, par scénario :
niveau prédit, niveau observé max, accord oui/non, TTC min, distance min,
collision, durée.

## Usage 3 — Rejeu en batch de tous les 24 scénarios

```bash
python3 apps/carla_replay.py --all --duree 15 --headless
```

Le flag `--headless` désactive le HUD Pygame pour un run rapide (utile pour
générer les figures de validation à intégrer au mémoire).

Un récapitulatif console affiche le nombre de scénarios avec accord et le
nombre avec collision observée dans CARLA.

## Logs et artefacts

- `logs/carla_YYYYMMDD_HHMMSS.csv` — log tick-par-tick d'une session
  interactive (`apps/carla_run.py`).
- `logs/rejeu_YYYYMMDD_HHMMSS.csv` — bilan d'un rejeu de scénarios
  (`apps/carla_replay.py`).

Les deux formats sont directement importables dans pandas / Excel.

## Dépannage

- **`RuntimeError: time-out of 10000ms`** — le serveur CARLA n'est pas prêt.
  Vérifie `host`/`port` dans le formulaire.
- **`Spawn refusé`** — point de spawn occupé. Relance ou change de carte.
- **HUD noir** — la caméra n'a pas encore reçu de frame. Attends 1-2 s.
- **Blueprint introuvable** — édite `world/carla_bridge.py`, dictionnaire
  `BLUEPRINTS`, et remplace par un blueprint disponible dans ta version.
- **Ego qui zigzague** — le pilotage latéral est très simple (gain P). Réduis
  le gain dans `pilotage_lateral` de `world/carla_control.py` (paramètre `gain`,
  défaut 0.8 — essayer 0.5).

## Usage 4 — Conduite libre (nouveau)

Vous conduisez l'ego au clavier, le monde CARLA vit tout seul (véhicules IA +
piétons), le moteur observe et affiche.

```bash
python3 apps/carla_freedrive.py
```

Dans le formulaire, onglet **Conduite libre** :
- Cochez « Mode conduite libre ».
- Choisissez la densité de trafic (véhicules IA, piétons IA).
- Choisissez le niveau d'assistance :
  - **Évaluation seule** : le moteur affiche, aucune intervention.
  - **Alerte** : + alerte visuelle en DANGER / CRITICAL.
  - **AEB** : + Automatic Emergency Braking si CRITICAL persistant (>0,4 s)
    et le conducteur ne freine pas déjà.
- Configurez la perception oracle (rayon en mètres, demi-angle du cône
  d'attention en degrés).

### Contrôles clavier

| Touche | Action |
|---|---|
| W / ↑ | Accélérer |
| S / ↓ | Freiner |
| A / ← | Tourner à gauche |
| D / → | Tourner à droite |
| Q     | Marche arrière (maintenir) |
| SHIFT | Frein à main |
| ESPACE| Pause |
| ESC   | Quitter |

### HUD spécifique à la conduite libre

- **Mini-carte radar** en bas à gauche : vue top-down centrée sur l'ego,
  cône d'attention teinté, acteurs colorés par niveau. Utile pour voir les
  côtés hors caméra.
- **Badge d'assistance** en bas à droite (EVAL / ALERTE / AEB) avec la
  mention « perception : oracle » pour être transparent sur la source.
- **Bandeau alerte pulsant** au-dessus du bandeau bas quand DANGER ou
  CRITICAL, rouge en AEB engagé.

### Log CSV

Le log inclut les colonnes usuelles + `assistance`, `aeb_engage`,
`conducteur_freine` — utile pour analyser après-coup les cas où l'AEB s'est
déclenché (ou aurait dû).


## Usage 5 — Trajet A vers B

Banc d'essai le plus simple : l'ego rejoint seul un point B depuis un point A
en suivant le reseau routier, le moteur pilotant le freinage.

```bash
# Route vide : test de reference
python3 apps/carla_trajet.py --distance 300

# En circulation : objectif zero collision
python3 apps/carla_trajet.py --distance 300 --vehicules 20 --pietons 10

# Avec le capteur d'obstacles statiques (murs, glissieres)
python3 apps/carla_trajet.py --distance 300 --obstacles
```

Deux modes, deux criteres de reussite distincts :

| Mode | Critere | Interpretation d'une alerte |
|---|---|---|
| Route vide (defaut) | **aucune alerte** | faux positif : defaut de perception |
| Avec trafic | **zero collision** + arrivee a B | normale : le moteur fait son travail |

Le mode route vide est le plus utile pour deboguer : sans aucun usager, toute
alerte est imputable a la chaine de perception (ecart lateral, capteur
d'obstacle) et non aux seuils du moteur. Lancer d'abord celui-la quand quelque
chose se comporte mal.

Le journal `logs/trajet_*.csv` contient une ligne par tick : temps, distance
parcourue, vitesse, niveau, nombre d'usagers percus, distance a l'obstacle
statique, et la recommandation d'action.
