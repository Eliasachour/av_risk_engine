"""
API FastAPI exposant le moteur de risque.

Endpoints :
  GET  /health              — sanity check
  GET  /enums               — listes des valeurs d'énumérations (pour les <select>)
  GET  /presets             — les 24 scénarios de référence (id, nom, niveau attendu)
  GET  /presets/{id}        — un scénario de référence complet
  POST /evaluate            — évalue un scénario à t=0
  POST /simulate            — simulation complète (frames + trajectoires)

Lancement local : python api.py ou uvicorn api:app --reload
"""
from __future__ import annotations

import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from risk_engine import (
    Agent,
    RiskConfig,
    ScenarioContext,
    assess_risk,
    format_seuils,
    tableau_metriques,
)
from risk_engine.context import (
    EtatRoute,
    Geometrie,
    Heure,
    Meteo,
    TypeAgent,
    TypeRoute,
)
from sim import diagnostic_collision, run

app = FastAPI(title="AV Risk Engine API", version="1.0")


@app.exception_handler(ValueError)
async def valueerror_handler(request, exc: ValueError):
    """Les entrées invalides (distance négative, etc.) renvoient un 400 lisible
    au lieu d'un 500 : le frontend affiche le message et ne se bloque plus."""
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# Le paramètre allow_origins=["*"] autorise toutes les requêtes (pratique pour tester).
# En production stricte, tu pourras remplacer "*" par l'URL publique de ton frontend Vite.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------- Schémas d'entrée --------------------------------


class AgentIn(BaseModel):
    type_agent: str
    vitesse_kmh: float
    distance_m: float
    cap_relatif_deg: float = 0.0
    acceleration_ms2: float = 0.0
    ecart_lateral_m: float = 0.0
    profondeur_mesuree: bool = True


class ScenarioIn(BaseModel):
    vitesse_ego_kmh: float
    type_route: str = "nationale"
    geometrie: str = "droite"
    limite_vitesse_kmh: int = 90
    zone_travaux: bool = False
    etat_route: str = "sec"
    meteo: str = "clair"
    heure: str = "jour"
    visibilite_m: float = 500.0
    agents: List[AgentIn] = Field(default_factory=list)


class SimulateIn(BaseModel):
    scenario: ScenarioIn
    reaction: bool = True


# ---------------------------- Conversions -------------------------------------


def _enum_lookup(enum_cls, val: str):
    for m in enum_cls:
        if m.value == val:
            return m
    raise HTTPException(status_code=400, detail=f"Valeur inconnue pour {enum_cls.__name__}: {val}")


def _to_ctx(s: ScenarioIn) -> ScenarioContext:
    return ScenarioContext(
        vitesse_ego_kmh=s.vitesse_ego_kmh,
        type_route=_enum_lookup(TypeRoute, s.type_route),
        geometrie=_enum_lookup(Geometrie, s.geometrie),
        limite_vitesse_kmh=s.limite_vitesse_kmh,
        zone_travaux=s.zone_travaux,
        etat_route=_enum_lookup(EtatRoute, s.etat_route),
        meteo=_enum_lookup(Meteo, s.meteo),
        heure=_enum_lookup(Heure, s.heure),
        visibilite_m=s.visibilite_m,
        agents=[
            Agent(
                type_agent=_enum_lookup(TypeAgent, a.type_agent),
                vitesse_kmh=a.vitesse_kmh,
                distance_m=a.distance_m,
                cap_relatif_deg=a.cap_relatif_deg,
                acceleration_ms2=a.acceleration_ms2,
                ecart_lateral_m=a.ecart_lateral_m,
                profondeur_mesuree=a.profondeur_mesuree,
            )
            for a in s.agents
        ],
    )


# ---------------------------- Endpoints ---------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/enums")
def enums():
    """Valeurs autorisées pour les <select> du frontend."""
    return {
        "type_route": [e.value for e in TypeRoute],
        "geometrie": [e.value for e in Geometrie],
        "etat_route": [e.value for e in EtatRoute],
        "meteo": [e.value for e in Meteo],
        "heure": [e.value for e in Heure],
        "type_agent": [e.value for e in TypeAgent],
    }


@app.get("/presets")
def presets():
    """Liste courte des scénarios de référence."""
    from calibration.scenarios_ref import REFERENCES
    return [
        {"id": r.id, "nom": r.nom, "famille": r.famille, "niveau_attendu": r.niveau_attendu.name}
        for r in REFERENCES
    ]


@app.get("/presets/{preset_id}")
def preset(preset_id: str):
    """Récupère un scénario complet (pour préremplir le formulaire)."""
    from calibration.scenarios_ref import REFERENCES
    for r in REFERENCES:
        if r.id == preset_id:
            c = r.ctx
            return {
                "id": r.id,
                "nom": r.nom,
                "niveau_attendu": r.niveau_attendu.name,
                "scenario": {
                    "vitesse_ego_kmh": c.vitesse_ego_kmh,
                    "type_route": c.type_route.value,
                    "geometrie": c.geometrie.value,
                    "limite_vitesse_kmh": c.limite_vitesse_kmh,
                    "zone_travaux": c.zone_travaux,
                    "etat_route": c.etat_route.value,
                    "meteo": c.meteo.value,
                    "heure": c.heure.value,
                    "visibilite_m": c.visibilite_m,
                    "agents": [
                        {
                            "type_agent": a.type_agent.value,
                            "vitesse_kmh": a.vitesse_kmh,
                            "distance_m": a.distance_m,
                            "cap_relatif_deg": a.cap_relatif_deg,
                            "acceleration_ms2": a.acceleration_ms2,
                            "ecart_lateral_m": a.ecart_lateral_m,
                            "profondeur_mesuree": a.profondeur_mesuree,
                        }
                        for a in c.agents
                    ],
                },
            }
    raise HTTPException(status_code=404, detail=f"Scénario {preset_id} introuvable")


@app.get("/seuils")
def seuils():
    """Grille des seuils de référence (pour l'affichage des jauges)."""
    cfg = RiskConfig()
    return {
        "TTC": {"safe": cfg.ttc_safe, "watch": cfg.ttc_watch, "danger": cfg.ttc_danger, "sens": "haut"},
        "THW": {"safe": cfg.thw_safe, "watch": cfg.thw_watch, "danger": cfg.thw_danger, "sens": "haut"},
        "PET": {"safe": cfg.pet_safe, "watch": cfg.pet_watch, "danger": cfg.pet_danger, "sens": "haut"},
        "CI": {"watch": cfg.ci_watch, "danger": cfg.ci_danger, "critical": cfg.ci_critical, "sens": "bas"},
        "DRAC": {"watch": cfg.drac_watch, "danger": cfg.drac_danger, "critical": cfg.drac_critical, "sens": "bas"},
        "RSS": {"mode": "binaire", "niveau_violation": cfg.rss_violation_level.name},
    }


@app.post("/evaluate")
def evaluate(scenario: ScenarioIn):
    """Évalue le risque à t=0 : par-agent (métriques, niveau, contributions) + global."""
    ctx = _to_ctx(scenario)
    a = assess_risk(ctx)
    table = tableau_metriques(ctx)

    return {
        "niveau_global": a.level.name,
        "avertissements": a.avertissements,
        "agents": [
            {
                "type": m.agent.type_agent.value,
                "distance": m.distance_m,
                "ttc": None if m.ttc == float("inf") else m.ttc,
                "thw": None if m.thw == float("inf") else m.thw,
                "pet": None if m.pet == float("inf") else m.pet,
                "rss": m.rss_min,
                "ratio_rss": None if m.ratio_rss == float("inf") else m.ratio_rss,
                "ci": m.ci,
                "drac": m.drac,
                "niveau": m.niveau.name,
                "niveaux_par_metrique": {k: v.name for k, v in m.niveaux.items()},
                "metrique_decisive": m.metrique_decisive,
                "metrique_impact": m.metrique_impact,
                "corroboration": m.corroboration,
                "contributions": m.contributions,
            }
            for m in table
        ],
    }


@app.post("/simulate")
def simulate(payload: SimulateIn):
    """Simulation complète : frames pour animation + courbes."""
    ctx = _to_ctx(payload.scenario)
    frames = run(ctx, reaction=payload.reaction)

    diag = diagnostic_collision(frames, ctx)
    from risk_engine import metrics as _m, modifiers as _mod
    mu_g = _mod.mu(ctx.etat_route) * _m.G

    return {
        "diagnostic": diag,
        "collision": any(f.collision for f in frames),
        "duree_s": frames[-1].t if frames else 0.0,
        "n_agents": len(ctx.agents),
        "types_agents": [a.type_agent.value for a in ctx.agents],
        "mu_g": mu_g,
        "geometrie": ctx.geometrie.value,
        "frames": [
            {
                "t": f.t,
                "niveau": f.assessment.level.name,
                "collision": f.collision,
                "ego": {
                    "x": f.ego.x,
                    "y": f.ego.y,
                    "vitesse_kmh": f.ego.speed_ms * 3.6,
                    "freinage": f.ego_accel < 0,
                },
                "agents": [
                    {
                        "x": s.x,
                        "y": s.y,
                        "niveau": (f.assessment.details[i].level.name
                                   if i < len(f.assessment.details) else "SAFE"),
                        "ttc": (None if f.assessment.details[i].ttc == float("inf")
                                else f.assessment.details[i].ttc)
                               if i < len(f.assessment.details) else None,
                        "thw": (None if f.assessment.details[i].thw == float("inf")
                                else f.assessment.details[i].thw)
                               if i < len(f.assessment.details) else None,
                        "distance": ((s.x - f.ego.x) ** 2 + (s.y - f.ego.y) ** 2) ** 0.5,
                        "rss": (f.assessment.details[i].rss_min
                                if i < len(f.assessment.details) else 0.0),
                        "drac": (f.assessment.details[i].drac
                                 if i < len(f.assessment.details) else 0.0),
                    }
                    for i, s in enumerate(f.agents)
                ],
            }
            for f in frames
        ],
    }


if __name__ == "__main__":
    import uvicorn
    # Récupère le port défini par Render, sinon utilise 8000 par défaut (pour le local)
    port = int(os.environ.get("PORT", 8000))
    # host="0.0.0.0" permet d'exposer l'API à l'extérieur du conteneur
    uvicorn.run("api:app", host="0.0.0.0", port=port)