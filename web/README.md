# AV Risk Engine — Interface web

Tableau de bord React (Vite + TypeScript) qui utilise l'API FastAPI du moteur.

## Démarrage

Deux terminaux, à la racine du projet :

```bash
# Terminal 1 — le backend FastAPI (port 8000)
python3 -m pip install fastapi uvicorn --break-system-packages
python3 api.py
# ou : uvicorn api:app --reload

# Terminal 2 — le frontend React (port 5173)
cd web
npm install
npm run dev
```

Puis ouvrir **http://localhost:5173** dans le navigateur.

Vite proxifie `/api/*` vers `http://127.0.0.1:8000` — pas de CORS à gérer en dev.

## Architecture

- **Panneau gauche** : formulaire scénario + préréglages (SC-01 à SC-24) +
  bouton "Simuler".
- **Panneau central** : évaluation à t = 0, se met à jour automatiquement à
  chaque modification (debounce 300ms). Niveau global, 6 cartes de métriques
  avec jauges et badges, classement d'impact.
- **Panneau droit** : simulation, avec deux onglets :
  - **Vue de dessus** : SVG animé, contrôle manuel via slider ou lecture
    automatique via bouton ▶ / ⏸.
  - **Courbes** : TTC par agent + vitesse ego dans le temps (Recharts).

## Endpoints API

| Méthode | Chemin | Description |
|---|---|---|
| GET | `/health` | Sanity check |
| GET | `/enums` | Valeurs autorisées pour les `<select>` |
| GET | `/presets` | Liste des 24 scénarios de référence |
| GET | `/presets/{id}` | Un scénario complet |
| GET | `/seuils` | Grille de seuils courante |
| POST | `/evaluate` | Évaluation à t = 0 |
| POST | `/simulate` | Simulation complète (frames) |

Documentation interactive : http://127.0.0.1:8000/docs (Swagger UI généré par
FastAPI).
