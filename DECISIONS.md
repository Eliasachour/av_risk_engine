# Registre des décisions de conception

Chaque décision non triviale du projet, au format court : **problème / options /
choix / justification**. But : rendre les choix traçables et défendables, et éviter
d'avoir à les reconstituer de mémoire.

---

### D1 — Décision par le pire des six niveaux
- Problème : comment agréger six métriques en un verdict unique ?
- Options : moyenne pondérée · vote · maximum.
- Choix : le **maximum** (pire niveau), par agent puis par scénario.
- Justification : garantit *par construction* qu'on ne sous-estime jamais le risque
  (zéro détection manquée). Une moyenne diluerait un signal critique isolé.

### D2 — RSS binaire, violation = DANGER (non optimisable)
- Problème : comment intégrer le modèle RSS, prouvé mais binaire, à une échelle graduée ?
- Options : bandes de ratio graduées · drapeau binaire.
- Choix : **binaire** (respecté → SAFE / violé → niveau unique DANGER), fidèle à
  Shalev-Shwartz ; la sévérité de la violation n'est **pas** un paramètre d'optimisation.
- Justification : RSS prouve une frontière, il ne note pas une criticité. Graduer
  serait une invention ; laisser l'optimiseur baisser ce niveau affaiblirait son sens.

### D3 — TTC effectif : marge contextuelle sur le seul TTC
- Problème : où appliquer la contextualisation (friction, VRU, visibilité, incertitude) ?
- Options : sur toutes les métriques · sur le seul TTC.
- Choix : marge appliquée au **TTC** (→ TTC effectif) ; les autres métriques restent brutes.
- Justification : concentre la contextualisation sur l'indicateur temporel de référence
  sans double comptage sur les métriques déjà physiques (DRAC, RSS).

### D4 — Pondération = explicabilité, pas décision
- Problème : comment savoir quelle métrique pèse le plus, sans casser la sécurité ?
- Options : remplacer le max par un score pondéré · ajouter une couche par-dessus.
- Choix : couche de **contribution** (criticité × pertinence) en lecture seule ; le
  max reste la décision. Sort la métrique la plus impactante + la corroboration.
- Justification : donne l'explicabilité et distingue verdict robuste/fragile sans
  toucher à la garantie de sécurité.

### D5 — Robustesse : borner et avertir (pas rejeter)
- Problème : que faire des entrées aberrantes (trop élevées, NaN) ?
- Options : rejeter · borner et signaler.
- Choix : **borner** dans le domaine physique et **avertir** ; le système ne bloque jamais.
- Justification : un moteur de sécurité doit rester opérant ; l'utilisateur est informé
  des corrections. (Les valeurs négatives restent, elles, refusées à la construction.)

### D6 — Freinage plafonné à l'adhérence µ·g
- Problème : le freinage du simulateur doit-il dépendre de la route ?
- Choix : décélération de l'ego **plafonnée à µ·g** selon l'état de la route.
- Justification : cohérence physique — sur sol glissant, on freine moins fort et la
  distance d'arrêt s'allonge. La météo agit alors en amont (alerte) et en aval (manœuvre).

### D7 — Freinage fondé sur la physique + diagnostic de collision
- Problème : le freinage keyé sur le niveau discret (table figée) pouvait sous-freiner,
  et le simulateur ne distinguait pas une collision inévitable d'un défaut de pilotage.
- Options : table niveau→décélération · verrou d'urgence à µ·g · **décélération requise**.
- Choix : l'ego freine de la **décélération réellement requise** pour s'arrêter quelques
  mètres avant le plus menaçant des agents *dans sa voie* (max sur les agents, façon
  DRAC), plafonnée à µ·g ; freinage proportionnel pour les croisements hors voie.
  Collision détectée image par image (arrêt à l'impact) + diagnostic évitable/inévitable
  (requis vs µ·g).
- Justification : physiquement correct et robuste au nombre d'agents (on répond au pire) ;
  évite toute collision *évitable* ; et rend explicite qu'une collision inévitable n'est
  pas un défaut de gestion mais une limite d'adhérence.

### D8 — Calibration : validation + optimisation sous contrainte, pas de boîte noire
- Problème : comment exploiter les données pour améliorer les seuils ?
- Options : classifieur appris (boîte noire) · optimisation sous contrainte d'un
  modèle à règles · régression logistique interprétable pour les poids.
- Choix : **optimisation sous contrainte** (zéro détection manquée puis min. fausses
  alarmes) par descente par coordonnées ; régression logistique en réserve pour les
  poids ; **pas** de classifieur boîte-noire.
- Justification : respecte les trois exigences — sécurité (contrainte dure),
  explicabilité (règles conservées), faible volume de données. Voir `optimize.py`.

### D9 — Moteur découplé de CARLA
- Problème : comment rester testable et calibrable sans dépendre de CARLA/GPU ?
- Choix : le moteur opère sur des structures pures ; la géométrie (`world/extraction.py`)
  est réutilisée à l'identique par le simulateur interne et par CARLA.
- Justification : rend le cœur testable (couverture ~93–100 %) et calibrable hors ligne ;
  l'intégration CARLA devient un simple adaptateur.

### D10 — Interface web découplée (React + FastAPI), cohérence servie par l'API
- Problème : offrir une interface moderne et accessible en ligne sans dupliquer la
  logique du moteur ni les règles de cohérence des paramètres.
- Options : réécrire la logique en JavaScript · Pyodide dans le navigateur ·
  API REST fine au-dessus du moteur + frontend séparé.
- Choix : **API FastAPI** (`api.py`) qui expose le moteur tel quel, et frontend
  **React + Vite + TypeScript** (`web/`) qui la consomme. Les règles de cohérence
  (météo ↔ état de route, visibilité, limites) restent dans
  `scenarios/constraints.py` et sont **servies** par l'endpoint `/contraintes` —
  une seule source de vérité, appliquée automatiquement dans le formulaire et
  vérifiée par `/evaluate` (avertissements).
- Justification : troisième interface du même moteur sans duplication — la
  démonstration concrète du découplage (D9). Les entrées invalides renvoient des
  erreurs 400 lisibles (jamais de 500), les requêtes en vol sont annulées côté
  client. Déployée publiquement sur Render (backend Web Service + frontend
  Static Site).

### D11 — Commande recommandée exportable par le moteur
- Problème : la logique de traduction *évaluation → commande véhicule* (décélération
  physique dans la voie, plafond µ·g, freinage proportionnel en croisement) vivait
  dans le simulateur (`sim/kinematic.py`). Elle allait devoir être dupliquée dans
  la glu CARLA (`world/carla_world.py`) au moment de brancher `VehicleControl`.
- Options : dupliquer (chaque environnement gère son contrôleur) · sortir la
  logique dans un module partagé du moteur.
- Choix : **module partagé `risk_engine/control.py`** — fonction pure
  `commande_recommandee(assessment, ctx, ego_x, ego_y, agents) → CommandeEgo`
  avec sortie normalisée (accélération m/s² *et* throttle/brake ∈ [0,1] pour
  branchement direct sur `carla.VehicleControl`). Le simulateur interne
  consomme désormais cette fonction ; la glu CARLA fera de même.
- Justification : source unique de vérité pour la commande. Aucun changement de
  comportement (89→89 tests inchangés + calibration identique) ; 7 tests dédiés
  verrouillent le contrat public du module. Le champ `steer` n'est pas exposé
  volontairement : le moteur ne modélise pas la trajectoire latérale — limite
  documentée. C'est le dernier pivot avant CARLA.
