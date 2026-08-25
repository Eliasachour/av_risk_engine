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
  explicabilité (règles conservées), faible volume de données. Voir `apps/optimize.py`.

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
- Choix : **API FastAPI** (`apps/api.py`) qui expose le moteur tel quel, et frontend
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
  comportement (suite de tests inchangée au moment du refactor + calibration
  identique) ; 7 tests dédiés
  verrouillent le contrat public du module. Le champ `steer` n'est pas exposé
  volontairement : le moteur ne modélise pas la trajectoire latérale — limite
  documentée. C'est le dernier pivot avant CARLA.

### D12 — Architecture d'intégration CARLA (perception + contrôle + HUD)
- Problème : brancher le moteur sur CARLA sans casser le découplage acquis et
  sans dupliquer la logique de contrôle.
- Options : (a) le moteur importe carla directement · (b) une glu séparée qui
  isole CARLA du moteur · (c) un service RPC qui expose le moteur à CARLA.
- Choix : **glu séparée** dans `world/carla_bridge.py`. Le moteur ignore
  toujours l'existence de CARLA. La glu convertit `carla.Actor` en
  `AgentObservation` (le même type consommé par le simulateur interne),
  appelle `refresh_context` → `assess_risk` → `commande_recommandee`, et
  applique la sortie via `VehicleControl`. Le pilotage latéral (waypoint
  following) reste hors du moteur : le moteur ne modélise pas la trajectoire
  latérale (limite documentée).
- Justification : conserve strictement le principe D9 (moteur découplé de son
  environnement), rend le portage vers un autre simulateur (LGSVL, etc.)
  trivial. Le contrôleur latéral simple est explicite et éditable en un
  endroit (fonction `_pilotage_lateral` dans `carla_run.py`).

### D13 — Mode conduite libre : perception oracle et assistance graduée
- Problème : offrir un mode où l'humain conduit dans un monde vivant avec le
  moteur qui observe en parallèle — sans le prétendre plus qu'il n'est.
- Options : (a) chaîne perception réelle par capteurs LiDAR/radar CARLA ·
  (b) perception « oracle » = vérité terrain filtrée par distance et cône ·
  (c) perception par simulation de bruits capteurs.
- Choix : **oracle filtrée + badge explicite dans le HUD**. Le rayon (60 m)
  et le cône (±60°) sont configurables. Le HUD affiche « perception : oracle »
  en permanence. La perception réelle est **documentée comme chantier séparé**.
- Justification : (b) permet de démontrer le moteur d'évaluation sans que la
  qualité de la perception ne bruite la démo. En soutenance, la transparence
  du badge évite toute sur-vente : « voici le moteur d'évaluation, dans une
  démo où la perception est parfaite ; brancher une perception réelle est un
  chantier propre et séparé ». Trois niveaux d'assistance sélectionnables
  (éval / alerte / AEB) permettent trois démos différentes sans dupliquer le
  code — argument-choc en soutenance : « regardez, je conduis, je fonce sur
  un piéton, l'AEB freine avant que je ne le heurte ».

### D14 — La décélération RSS plafonnée à l'adhérence disponible
- Problème : le modèle RSS de Shalev-Shwartz paramètre la décélération garantie
  de l'ego (`b_min`, défaut 4 m/s²) et la décélération maximale supposée du
  véhicule de tête (`b_max`, défaut 8 m/s²). Ces constantes étaient appliquées
  **quel que soit l'état de la chaussée**. Or sur verglas, l'adhérence
  disponible tombe à µ·g ≈ 2,9 m/s² : promettre 4 m/s² est physiquement
  impossible et **sous-estime la distance de sécurité exactement là où il
  faudrait être le plus prudent**. Mesure : à 90 km/h sur verglas, le RSS
  exigeait 66 m alors que la distance d'arrêt physique est de 106 m.
- Options : (a) laisser les constantes (statu quo) · (b) plafonner `b_min` à
  µ·g · (c) plafonner `b_min` **et** `b_max` à µ·g.
- Choix : **(b) — plafonner `b_min` seulement**, via `b_min_eff = min(cfg.b_min, µ·g)`.
- Justification : `b_min` décrit ce que l'ego *peut réellement faire* — c'est
  une contrainte physique dure, la plafonner est une correction de justesse.
  `b_max`, en revanche, est une hypothèse *pessimiste* sur le comportement de
  l'autre véhicule ; la relâcher sur sol dégradé ferait **baisser** la distance
  de sécurité exigée (le leader freine moins fort donc parcourt plus de
  distance). Mathématiquement correct, mais contraire à la vocation d'un
  système de sécurité — on garde donc l'hypothèse pessimiste. Choix
  conservateur assumé et documenté.
- Effet mesuré : sur verglas à 90 km/h en suivi, RSS passe de 66,4 m à 96,7 m
  et le niveau de SAFE à DANGER — un danger réel que le moteur ratait. Sur sec,
  mouillé et neigeux (µ·g > 4 m/s²), aucun changement. **Calibration
  inchangée** (0 détection manquée · 8 fausses alarmes · 16/24) car le jeu de
  référence ne contient pas de cas verglas + suivi longitudinal.
- Verrouillé par deux invariants : `test_rss_croit_quand_l_adherence_baisse` et
  `test_rss_jamais_inferieur_a_la_distance_d_arret_sur_sol_degrade`.
- Limite restante : les valeurs `rho=0.5`, `a_accel=2.0`, `b_max=8.0` restent
  des choix de conception documentés dans `RiskConfig`, pas des mesures. Un jury
  peut légitimement demander leur justification — la réponse est qu'ils
  proviennent de l'article RSS original et de la littérature ADAS, et qu'ils
  sont exposés en paramètres pour être ajustables.

### D15 — PET géométrique 2D et retrait du TTC hors de son domaine de validité
- Problème : les fausses alarmes sur piétons traversants (SC-03, SC-12, SC-13)
  venaient du TTC, non du PET. Le TTC suppose un rapprochement colinéaire ;
  face à une traversée perpendiculaire il mesure une grandeur sans
  signification physique (Westhofen et al.). Le PET, lui, était une estimation
  « snapshot » qui renvoyait `distance / v_ego` **indépendamment de l'écart
  latéral** : un piéton à 10 m sur le côté avait le même PET qu'un piéton dans
  la voie.
- Options explorées, toutes **mesurées** sur les 24 scénarios :
  1. Plafonner la marge contextuelle — **rejeté** : 1 détection manquée dès un
     plafond de ×2,0. Les marges fortes (×4,88) portent sur SC-15 et SC-21,
     piétons de nuit correctement classés CRITICAL.
  2. Plafonner la marge pour les seuls usagers motorisés — **rejeté** :
     2 détections manquées (SC-11, SC-20, obstacles sur sol dégradé, qui ont
     besoin du facteur de friction).
  3. Déclasser quand une seule métrique déclenche — **rejeté** : les 8 fausses
     alarmes ont une corroboration de 1/6, mais **8 des 13 vrais
     DANGER/CRITICAL aussi**. Le critère ne discrimine rien.
  4. PET 2D seul — **sans effet** : écart total 10 contre 9, car le PET n'était
     pas la métrique décisive de ces cas.
  5. Retrait du TTC en croisement seul — **rejeté** : 4 détections manquées.
  6. **PET 2D + retrait du TTC en croisement** — retenu.
- Choix : trois modifications indissociables.
  - `metrics.pet_2d` construit réellement la zone de conflit : créneau
    d'occupation du couloir de l'ego par l'agent, créneau d'occupation de la
    zone longitudinale par l'ego, PET = écart entre les deux (0 si
    recouvrement).
  - Un **horizon de confiance** de 4 s : au-delà, le PET n'est pas renseigné.
    Prédire qu'un piéton entrera dans la voie dans six secondes suppose une
    vitesse constante pendant six secondes — cela relève de l'intention, pas de
    la cinématique. Le plateau sûr mesuré s'étend de 2,5 s à 5,0 s ; 4,0 s est
    retenu comme milieu de plateau et par alignement sur le T_ref de l'indice
    de criticité, plutôt que l'optimum apparent de 2,5 s adjacent à une
    violation de sécurité.
  - Le PET est désormais divisé par la marge contextuelle, comme le TTC. Sans
    cela la vulnérabilité de l'usager cesserait d'agir en croisement,
    précisément là où elle importe le plus.
- Géométrie extraite dans `risk_engine/geometry.py`, partagée avec
  `sim/kinematic.py` : le moteur et le simulateur placent les agents à
  l'identique. Toute divergence serait un bug silencieux.
- Effet mesuré : **16/24 → 17/24 (71 %)**, fausses alarmes **8 → 7**,
  détections manquées **0 → 0**. SC-12 passe de WATCH à SAFE (correct).
- Verrouillé par 12 tests dédiés (`tests/test_pet_2d.py`), dont un qui
  **documente une régression attendue** : retirer le TTC sans PET 2D doit
  produire des détections manquées.
- Un test existant a dû être révisé. `test_vru_plus_conservateur` exigeait un
  niveau *strictement* supérieur pour un VRU ; ce n'est pas un invariant valide
  avec des métriques en bandes, aucune modulation monotone ne garantissant un
  franchissement de bande. Le test assertait un effet de bord de l'ancienne
  géométrie, pas la propriété. Il vérifie désormais, plus fortement : niveau
  jamais inférieur, marge strictement supérieure, et métrique temporelle
  effective strictement plus courte.
- Limite restante : le PET 2D suppose des trajectoires rectilignes à vitesse
  constante sur l'horizon. La prédiction d'intention reste hors périmètre.

### D16 — L'écart latéral doit venir de la perception, et le VRU longeant peut être rétrogradé
- Problème : en conduite libre, le moteur passait en CRITICAL en permanence et
  le mode AEB rendait la conduite impossible. Deux causes distinctes.
- **Cause 1 — écart latéral jamais calculé.** `agent_from_observation`
  (`world/extraction.py`) ne renseignait pas `ecart_lateral_m`. Tout agent perçu
  depuis CARLA arrivait donc avec un écart nul, c'est-à-dire **considéré comme
  étant dans la voie de l'ego** : voitures garées, véhicules en sens inverse et
  piétons de trottoir devenaient tous des conflits frontaux. Le filtrage latéral
  (D8), conçu exactement pour ce cas, ne pouvait jamais s'activer. Corrigé par
  projection sur la normale au cap de l'ego. Mesure sur une scène urbaine :
  niveau global **CRITICAL → DANGER**, voiture garée **DANGER → SAFE**, véhicule
  en sens inverse **CRITICAL → WATCH**.
- **Cause 2 — la règle « ne jamais rétrograder un VRU » était trop grossière.**
  Elle ne distinguait pas un piéton qui *traverse* d'un piéton qui *longe* la
  route. Or lever l'exemption globalement n'était pas envisageable : mesuré,
  SC-21 (piéton de nuit, étiqueté CRITICAL) a un facteur de menace de 0,00 et
  serait rétrogradé, donc **manqué**. La règle est donc affinée : un VRU n'est
  protégé de la rétrogradation que si son conflit est de **famille croisement**.
  Un VRU longeant la route, sans composante transversale, redevient
  rétrogradable comme tout agent. Calibration inchangée (17/24, 0 manquée) :
  tous les VRU du jeu de référence traversent.
- **Cause 3 — obstacle fantôme à 0 m.** Le capteur d'obstacle était monté trop
  bas avec un rayon de capsule trop large : celle-ci descendait sous le niveau
  du sol et détectait la chaussée à chaque tick. Filtrage en cinq étapes :
  distance crédible, surface de roulement, acteur déjà suivi, appartenance au
  couloir carrossable, confirmation sur plusieurs ticks.
- Verrouillé par 6 tests d'intégration supplémentaires, dont
  `test_pieton_qui_longe_le_trottoir_est_safe` et sa contrepartie
  `test_pieton_qui_traverse_reste_detecte`.
- Leçon : ces trois défauts étaient invisibles sur les 24 scénarios de
  référence, qui fournissent l'écart latéral explicitement et ne contiennent ni
  décor ni acteurs de fond. **Un jeu de scénarios scriptés ne teste pas la
  chaîne de perception** — seul un environnement ouvert le fait.

### D17 — Trajet A → B : deux modes, deux critères de réussite
- Problème : valider l'intégration demandait un banc d'essai plus simple que le
  mode conduite libre, où trafic, piétons et conduite humaine se mêlent au point
  qu'un comportement anormal n'est imputable à rien de précis.
- Choix : un script de trajet point à point (`apps/carla_trajet.py`) avec **deux
  régimes explicites**, chacun assorti de son propre critère.
  - **Route vide** (défaut) — critère : *aucune alerte*. Sans usager, toute
    alerte est par construction un faux positif, donc imputable à la chaîne de
    perception et non aux seuils du moteur. C'est le mode à lancer en premier
    quand quelque chose se comporte mal.
  - **En circulation** (`--vehicules N --pietons M`) — critère : *zéro collision
    et arrivée à destination*. Les alertes y sont normales : c'est le travail du
    moteur de les produire. La double condition importe : un ego qui freinerait
    indéfiniment éviterait certes toute collision, mais échouerait aussi.
- Le freinage vient de `commande_recommandee` (D11) : décélération réellement
  requise, plafonnée à µ·g. Le pilotage latéral suit l'itinéraire, hors moteur.
- Mesures : route vide → niveau maximal SAFE, 0 collision. 15 véhicules et
  8 piétons → maximum WATCH, 0 collision. 40 véhicules et 20 piétons →
  maximum DANGER, 0 collision, destination atteinte.
- Verrouillé par deux tests exécutant le script de bout en bout contre le double
  de test CARLA.

### D18 — Disponibilité de CARLA vérifiée à l'appel, pas à l'import
- Problème : les modules d'intégration figeaient la disponibilité de `carla`
  dans un drapeau évalué au moment de l'import. Un module chargé avant que
  `carla` ne soit disponible restait inutilisable pour toute la durée du
  processus, et l'erreur ne se manifestait que selon l'ordre des imports —
  symptôme classiquement attribué à tort à l'environnement.
- Choix : une fonction `_carla_disponible()` qui tente l'import à chaque appel.
- Détecté par la suite de tests : deux tests passaient isolément mais échouaient
  en suite complète, un import antérieur ayant figé le drapeau à faux.

### D19 — Provenance des poids de pertinence, et leur sensibilité mesurée
- Question : d'où viennent les valeurs de `weighting.POIDS` — notamment les
  intermédiaires comme 0,7 pour le TTC en croisement ?
- **Ce qui est fondé.** La structure en 0 et 1 découle des domaines de validité
  établis par Westhofen et al. Un poids nul signifie « cette métrique ne mesure
  rien d'interprétable dans ce régime » : le THW est un temps inter-véhiculaire,
  sans objet face à une traversée ; le PET mesure une coïncidence de
  trajectoires, sans objet en suivi ; la borne RSS est prouvée pour le seul
  suivi longitudinal. Ces zéros ne sont pas des réglages, ce sont des
  constats de non-applicabilité.
- **Ce qui ne l'est pas.** Les valeurs intermédiaires (0,7 · 0,8 · 0,6 · 0,3)
  sont un **jugement d'ingénierie**, pas une mesure. Westhofen fournit une
  analyse *qualitative* d'adéquation (adapté / partiellement adapté / inadapté)
  et non des coefficients ; traduire « partiellement adapté » par 0,7 est une
  interprétation qui nous appartient. Il faut le dire ainsi.
- **Ce que cela change, mesuré.** Perturbation systématique des poids
  intermédiaires sur les 24 scénarios de référence :

  | Variante | Niveaux changés | Métrique décisive changée | Métrique d'impact changée |
  |---|---|---|---|
  | intermédiaires ±0,2 | 0/24 | 0/24 | **0/24** |
  | tous ramenés à 0,5 | 0/24 | 0/24 | **0/24** |
  | tous ramenés à 1,0 | 0/24 | 0/24 | 5/24 |
  | binaire strict (0 ou 1) | 0/24 | 0/24 | 5/24 |

- **Lecture.** Le niveau de risque et la métrique décisive ne bougent jamais :
  confirmation expérimentale de D4, la pondération n'entre pas dans la décision.
  Quant à la métrique d'impact, elle est **insensible à la valeur exacte** des
  poids intermédiaires — les faire varier de ±0,2 ou les aplatir à 0,5 ne change
  rien. Seule compte l'existence d'une **graduation sous 1** : la supprimer
  modifie la métrique reportée dans 5 scénarios sur 24.
- **Conclusion défendable.** Ces coefficients n'ont pas besoin d'être justifiés
  au dixième près, et prétendre le contraire serait malhonnête. Ce qui est
  fondé, c'est la hiérarchie — pleinement pertinent, partiellement pertinent,
  non applicable — et la mesure ci-dessus montre que c'est la seule chose dont
  dépende la sortie.
- Perspective : une régression logistique sur un jeu élargi (~50 scénarios
  étiquetés) permettrait d'estimer ces poids au lieu de les poser.

### D20 — Raisonnement par voie : la géométrie euclidienne échoue en virage
- Problème mesuré : un véhicule **immobile, dans la voie de l'ego, à 40 m** est
  classé SAFE dès que la route tourne. L'écart latéral euclidien croît avec la
  courbure — 4 m sur un rayon de 200 m, 9,8 m sur 80 m — au point de faire
  rétrograder l'agent par le filtrage latéral (D8). C'est une **détection
  manquée**, ce que le moteur s'interdit. Le même défaut affectait le cap : un
  véhicule de la voie adjacente présente un écart de cap absolu non nul, dû à
  la seule courbure ; extrapolé en ligne droite, il faisait croire à une
  convergence et le classait CRITICAL.
- Choix : un module `world/lane_relation.py` qui exploite les waypoints CARLA
  (`road_id`, `lane_id`, `section_id`, orientation de voie) pour produire :
  - la **relation** entre les deux véhicules — même voie, voie adjacente, voie
    opposée, route différente, ou **convergente** (routes distinctes qui se
    rejoignent devant, typiquement une intersection) ;
  - un **écart latéral curviligne**, exprimé en nombre de voies le long de la
    route et non à vol d'oiseau ;
  - un **cap relatif mesuré par rapport aux directions de voie**, de sorte que
    deux véhicules suivant chacun leur voie donnent 0°.
- Le module vit dans `world/` : le moteur reste ignorant de CARLA (D9). Il ne
  reçoit qu'un écart latéral et un cap — simplement, mesurés le long de la
  route. Sans carte, on retombe sur l'euclidien : le simulateur cinématique et
  les 24 scénarios de référence sont inchangés.
- Effets mesurés sur route courbe (rayon ≈ 118 m) :
  - obstacle immobile même voie à 40 m : écart −6,70 m → **+0,00 m**, niveau
    SAFE → **DANGER** (détection récupérée) ;
  - véhicule voie adjacente à 10 m, même vitesse : **CRITICAL → SAFE** ;
  - même voie, voie opposée et adjacente correctement distinguées.
- Limite restante : un véhicule de la voie opposée reste classé WATCH et non
  SAFE, le filtrage latéral ne rétrogradant que de deux crans au maximum. Ce
  plafond est une marge de sécurité délibérée, désormais exposée
  (`RiskConfig.retrogradation_crans`). Le porter à 3 autorise la descente
  jusqu'à SAFE ; mesuré sans effet sur les 24 scénarios — mais **aucun d'eux
  n'exerce ce chemin**, la mesure ne vaut donc pas preuve de sûreté. Laissé
  désactivé par défaut.

### D21 — Quatre scénarios de trafic et imprévisibilité contextuelle
- Problème : disposer de régimes de trafic distincts et reproductibles, dont
  un présentant des comportements inattendus — sans tomber dans le hasard pur,
  qui produit des véhicules incohérents et fausse l'évaluation du risque.
- Choix : quatre scénarios (`normal`, `peu dense`, `dense`, `imprévisible`)
  portés par `world/traffic.py`. Les trois premiers ne diffèrent que par la
  densité et les plages de réglage du Traffic Manager. Le quatrième reprend la
  densité du troisième et ajoute des **écarts de conduite** suivant la chaîne
  *situation → personnalité → candidats plausibles → décision → durée*.
- Trois garde-fous, issus de défauts mesurés sur une version antérieure :
  1. **Le type d'écart est choisi parmi les candidats plausibles**, jamais tiré
     puis vérifié. Mesuré sur la version précédente : 55 % des déclenchements
     ne produisaient aucune action tout en immobilisant le véhicule pendant
     2 à 5 s, le chaînage `elif` retombant dans le vide.
  2. **La propension s'exprime par seconde**, évaluée toutes les 0,5 s. Un taux
     par image dépendait du tick rate : 47 écarts/min à 20 Hz contre 71 à
     30 Hz, donc la même graine ne rejouait pas la même simulation.
  3. **Un générateur par véhicule**, dérivé de la graine et de l'identifiant :
     le comportement d'un véhicule ne dépend plus de l'ordre de traitement des
     autres.
- Un écart n'est envisagé que s'il a du sens : pas d'insertion sans véhicule
  devant, pas d'hésitation hors intersection, pas de freinage brusque à
  l'arrêt, pas d'insertion forcée pour un conducteur prudent.
- Quatre personnalités (Prudent, Normal, Pressé, Distrait) réparties 30/40/15/15.
- Journal structuré (`world/simulation_log.py`) : un flux pour les évaluations
  de risque avec leurs justifications (relation de voie, distance, vitesse
  relative, TTC, niveau), un pour les écarts de conduite. Seules les lignes
  informatives sont écrites — non-SAFE et transitions — sinon cinquante
  véhicules produiraient des dizaines de milliers de lignes identiques.
- **Validation partielle, à assumer** : la mécanique d'écarts est vérifiée par
  tests à situations injectées (déclenchement, reproductibilité, modulation par
  l'intensité, respect du repos). En revanche le double de test CARLA ne fait
  pas rouler les véhicules — leur vitesse reste nulle — donc les écarts ne
  peuvent pas s'y déclencher et la **dynamique du trafic dense reste à valider
  sur le vrai CARLA**.
