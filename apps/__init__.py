"""Points d'entree executables du projet av_risk_engine.

Chaque module de ce paquet est un script autonome qui se lance depuis la racine
du depot, par exemple :

    python3 apps/calibrate.py
    python3 apps/carla_run.py
    uvicorn apps.api:app --host 0.0.0.0 --port 8000

Les modules metier (`risk_engine`, `sim`, `scenarios`, `calibration`, `world`)
restent a la racine. Ce fichier ajoute la racine du depot au ``sys.path`` pour
que les imports fonctionnent quand on lance un script depuis n'importe ou.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ajouter la racine du depot (parent de ce fichier) au sys.path si absent.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
