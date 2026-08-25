"""
Point d'entrée : ouvre le formulaire, construit le scénario, évalue le risque.

L'étape suivante (paquet `world/`) appliquera le ScenarioContext à CARLA
(réglage météo, spawn des agents) et lancera la boucle synchrone qui réévalue
le risque à chaque frame.
"""

# Ajoute la racine du depot au sys.path pour permettre les imports metier
# (risk_engine, sim, scenarios, calibration, world) meme quand ce script est
# lance directement (`python3 apps/foo.py`). Voir apps/__init__.py.
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from risk_engine import assess_risk
from scenarios.form import demander_scenario


def main() -> None:
    res = demander_scenario()
    if res is None:
        print("Saisie annulée.")
        return
    ctx, _reaction = res  # la réaction de l'ego servira à la boucle CARLA (étape world/)

    print("Scénario saisi :", ctx)
    evaluation = assess_risk(ctx)
    print("Évaluation :", evaluation)
    for d in evaluation.details:
        print(f"  - {d.agent.type_agent.value:9s} | {d.level!s:8s} | {d.raison}")

    # TODO (étape world/) :
    #   1. régler la météo CARLA à partir de ctx (carla.WeatherParameters)
    #   2. charger la carte / le tronçon selon ctx.type_route, ctx.geometrie
    #   3. spawn de l'ego et des agents (positions selon distance/cap)
    #   4. boucle en mode synchrone : à chaque frame, reconstruire un ScenarioContext
    #      depuis le monde, appeler assess_risk, journaliser, et (option) intervenir.


if __name__ == "__main__":
    main()
