"""
Règles de cohérence d'un scénario, modélisées comme des DONNÉES.

Objectif : empêcher les combinaisons absurdes (« pluie + route sèche ») et fournir,
à l'interface de saisie, la liste des options compatibles pour chaque champ.

Ce module est pur (pas de tkinter, pas de CARLA) et donc testable seul. Il définit
le « domaine de validité » du scénario logique (au sens PEGASUS).
"""
from __future__ import annotations

from typing import List, Tuple

from risk_engine.context import EtatRoute, Heure, Meteo, ScenarioContext, TypeRoute

# --- État de route compatible avec la météo ---
COMPAT_METEO_ROUTE = {
    Meteo.CLAIR: [EtatRoute.SEC],
    Meteo.PLUIE: [EtatRoute.MOUILLE],
    Meteo.NEIGE: [EtatRoute.NEIGEUX, EtatRoute.VERGLAS],
    Meteo.BROUILLARD: [EtatRoute.SEC, EtatRoute.MOUILLE],
}

# --- Plage de visibilité plausible selon la météo (m), de jour ---
VIS_METEO = {
    Meteo.CLAIR: (300.0, 500.0),
    Meteo.PLUIE: (100.0, 300.0),
    Meteo.NEIGE: (60.0, 200.0),
    Meteo.BROUILLARD: (20.0, 150.0),
}
FACTEUR_NUIT = 0.6  # la nuit rabote la portée visuelle utile

# --- Limites de vitesse plausibles selon le type de route (km/h) ---
LIMITES_ROUTE = {
    TypeRoute.AUTOROUTE: [110, 130],
    TypeRoute.NATIONALE: [80, 90],
    TypeRoute.DEPARTEMENTALE: [80],
    TypeRoute.URBAIN: [30, 50],
}
ZONE_TRAVAUX_LIMITES = [30, 50, 70, 90]  # limites temporaires possibles en zone de travaux

MARGE_VITESSE_EGO = 1.2  # la vitesse ego ne doit pas excéder la limite de plus de 20 %


def etats_route_compatibles(meteo: Meteo) -> List[EtatRoute]:
    return list(COMPAT_METEO_ROUTE[meteo])


def plage_visibilite(meteo: Meteo, heure: Heure = Heure.JOUR) -> Tuple[float, float]:
    vmin, vmax = VIS_METEO[meteo]
    if heure == Heure.NUIT:
        vmin, vmax = vmin * FACTEUR_NUIT, vmax * FACTEUR_NUIT
    return vmin, vmax


def limites_compatibles(type_route: TypeRoute, zone_travaux: bool = False) -> List[int]:
    base = list(LIMITES_ROUTE[type_route])
    if zone_travaux:
        mx = max(base)
        base = base + [v for v in ZONE_TRAVAUX_LIMITES if v < mx]
    return sorted(set(base))


def valider(ctx: ScenarioContext) -> List[str]:
    """Renvoie la liste des incohérences (vide = scénario cohérent)."""
    problemes: List[str] = []

    if ctx.etat_route not in etats_route_compatibles(ctx.meteo):
        attendus = ", ".join(e.value for e in etats_route_compatibles(ctx.meteo))
        problemes.append(
            f"État de route '{ctx.etat_route.value}' incompatible avec météo "
            f"'{ctx.meteo.value}' (attendu : {attendus})."
        )

    vmin, vmax = plage_visibilite(ctx.meteo, ctx.heure)
    if ctx.visibilite_m > vmax * 1.05:
        problemes.append(
            f"Visibilité {ctx.visibilite_m:.0f} m trop élevée pour "
            f"'{ctx.meteo.value}' de {ctx.heure.value} (max ~{vmax:.0f} m)."
        )
    elif ctx.visibilite_m < vmin * 0.5:
        problemes.append(
            f"Visibilité {ctx.visibilite_m:.0f} m anormalement basse pour ce contexte."
        )

    limites = limites_compatibles(ctx.type_route, ctx.zone_travaux)
    if ctx.limite_vitesse_kmh not in limites:
        problemes.append(
            f"Limite {ctx.limite_vitesse_kmh:.0f} km/h non plausible pour une route "
            f"'{ctx.type_route.value}'"
            f"{' en zone de travaux' if ctx.zone_travaux else ''} "
            f"(attendu : {limites})."
        )

    if ctx.vitesse_ego_kmh > ctx.limite_vitesse_kmh * MARGE_VITESSE_EGO:
        problemes.append(
            f"Vitesse ego {ctx.vitesse_ego_kmh:.0f} km/h excède trop la limite "
            f"{ctx.limite_vitesse_kmh:.0f} km/h."
        )

    return problemes


def est_coherent(ctx: ScenarioContext) -> bool:
    return len(valider(ctx)) == 0
