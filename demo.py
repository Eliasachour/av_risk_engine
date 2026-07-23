"""Démonstration : évaluation de SC-02 (freinage brusque) et SC-06 (multi-agents)."""
from risk_engine import Agent, ScenarioContext, TypeAgent, assess_risk


def montrer(nom, ctx):
    r = assess_risk(ctx)
    print(f"\n=== {nom} ===")
    print(r)
    for d in r.details:
        print(f"  - {d.agent.type_agent.value:9s} | {d.level!s:8s} | {d.raison}")


# SC-02 : freinage brusque du véhicule de tête
sc02 = ScenarioContext(
    vitesse_ego_kmh=90,
    agents=[Agent(TypeAgent.VOITURE, vitesse_kmh=30, distance_m=40, cap_relatif_deg=0,
                  acceleration_ms2=-8.0)],
)

# SC-06 : multi-agents (voiture en sens inverse + cycliste traversant)
sc06 = ScenarioContext(
    vitesse_ego_kmh=85,
    agents=[
        Agent(TypeAgent.VOITURE, vitesse_kmh=120, distance_m=200, cap_relatif_deg=180),
        Agent(TypeAgent.CYCLISTE, vitesse_kmh=15, distance_m=25, cap_relatif_deg=45),
    ],
)

if __name__ == "__main__":
    montrer("SC-02 Freinage brusque", sc02)
    montrer("SC-06 Multi-agents", sc06)
