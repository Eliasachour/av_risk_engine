#!/usr/bin/env python3
"""
Calibration du moteur contre le jeu de scénarios de référence.

Usage :
    python calibrate.py            # évalue avec la configuration par défaut
    python calibrate.py --details  # ajoute le détail des métriques par scénario

Les niveaux attendus se modifient dans calibration/scenarios_ref.py.
"""
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
