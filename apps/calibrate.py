#!/usr/bin/env python3
"""
Calibration du moteur contre le jeu de scénarios de référence.

Usage :
    python calibrate.py            # évalue avec la configuration par défaut
    python calibrate.py --details  # ajoute le détail des métriques par scénario

Les niveaux attendus se modifient dans calibration/scenarios_ref.py.
"""

# Ajoute la racine du depot au sys.path pour permettre les imports metier
# (risk_engine, sim, scenarios, calibration, world) meme quand ce script est
# lance directement (`python3 apps/foo.py`). Voir apps/__init__.py.
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import sys

from calibration import REFERENCES, evaluer, format_rapport
from risk_engine import RiskConfig, tableau_metriques, format_tableau


def main() -> None:
    cfg = RiskConfig()
    res = evaluer(cfg)
    print(f"=== Calibration du moteur sur {len(res)} scénarios de référence ===\n")
    print(format_rapport(res))

    if "--details" in sys.argv:
        print("\n=== Détail des métriques par scénario ===")
        for cas in REFERENCES:
            print(f"\n{cas.id} — {cas.nom} ({cas.famille})")
            print(format_tableau(tableau_metriques(cas.ctx, cfg)))


if __name__ == "__main__":
    main()
