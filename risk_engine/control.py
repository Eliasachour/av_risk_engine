"""
Commande de conduite recommandée par le moteur — pure et exportable.

Ce module isole la logique de traduction *évaluation de risque → commande
véhicule*, jusqu'ici enfouie dans le simulateur (`sim/kinematic.py`). L'isoler
permet de la partager entre le simulateur interne et l'intégration CARLA
(`world/carla_world.py`) sans duplication.

**Ce module est pur** : entrées explicites, aucune dépendance à CARLA, aucun
effet de bord. Il calcule seulement *ce qu'il faudrait faire* ; c'est à
l'appelant (simulateur ou pont CARLA) d'appliquer la commande à son actionneur.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from . import metrics, modifiers
from .context import ScenarioContext
from .engine import RiskAssessment, RiskLevel

# ----------------------------------------------------------------------------
# Constantes de conception (mêmes valeurs que le simulateur historique).
# ----------------------------------------------------------------------------

#: Décélérations *visées* par niveau (m/s²) hors mode d'urgence physique.
#: Elles seront plafonnées à l'adhérence µ·g par le contrôleur.
FREINAGE_PAR_NIVEAU = {
    RiskLevel.SAFE: 0.0,
    RiskLevel.WATCH: -2.0,
    RiskLevel.DANGER: -5.0,
    RiskLevel.CRITICAL: -8.0,
}

#: Marge d'arrêt : viser l'arrêt N mètres AVANT l'agent le plus menaçant.
MARGE_ARRET_M = 6.0

#: Demi-largeur de voie utilisée pour déterminer « dans la voie devant ».
DEMI_VOIE_M = 2.5


# ----------------------------------------------------------------------------
# Types de sortie.
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandeEgo:
    """Commande recommandée par le moteur pour l'ego.

    Attributs
    ---------
    acceleration_ms2 : float
        Accélération commandée en m/s² (négative = freinage). Toujours plafonnée
        à ``[-mu_g, +mu_g]``.
    throttle : float
        Fraction d'accélérateur dans ``[0, 1]`` — 0 si on freine ou si SAFE.
    brake : float
        Fraction de frein dans ``[0, 1]`` — proportionnelle à la décélération
        commandée relativement à µ·g.
    mode : str
        Étiquette lisible : ``"nominal"`` (SAFE, pas d'action), ``"proportionnel"``
        (freinage proportionnel au niveau, croisement typique) ou ``"physique"``
        (freinage sur décélération réellement requise, agent dans la voie).
    mu_g : float
        Adhérence disponible utilisée pour le plafonnement (m/s²).

    Notes
    -----
    Le champ ``steer`` n'est *pas* exposé : le moteur ne modélise pas la
    trajectoire latérale (limite documentée). L'appelant est libre d'ajouter son
    propre pilotage latéral.
    """
    acceleration_ms2: float
    throttle: float
    brake: float
    mode: str
    mu_g: float


@dataclass(frozen=True)
class ObsAgent:
    """Vue minimaliste d'un agent, du seul point de vue du contrôleur.

    On ne prend que ce qui compte pour décider si l'agent est *dans la voie
    devant l'ego* et à quelle distance. Les métriques (TTC, DRAC, …) viennent,
    elles, du ``RiskAssessment`` déjà calculé en amont.
    """
    x: float                #: position longitudinale (m, repère monde)
    y: float                #: position latérale (m, repère monde)
    drac: float             #: décélération requise pour éviter l'agent (m/s²)


# ----------------------------------------------------------------------------
# Helpers.
# ----------------------------------------------------------------------------


def _dans_la_voie_devant(agent_x: float, agent_y: float,
                         ego_x: float, ego_y: float,
                         demi_voie: float = DEMI_VOIE_M) -> bool:
    """Vrai si l'agent est *devant* l'ego et à faible séparation latérale."""
    return (agent_x - ego_x) > 0.2 and abs(agent_y - ego_y) < demi_voie


# ----------------------------------------------------------------------------
# Fonction principale : la commande recommandée.
# ----------------------------------------------------------------------------


def commande_recommandee(
    assessment: RiskAssessment,
    ctx: ScenarioContext,
    ego_x: float,
    ego_y: float,
    agents: Iterable[ObsAgent],
) -> CommandeEgo:
    """Traduit une évaluation de risque en commande véhicule.

    La logique reproduit celle du simulateur historique, en l'exposant proprement :

    1. Si un agent est *dans la voie devant* et a un DRAC > 0, on freine de la
       décélération réellement requise pour s'arrêter ``MARGE_ARRET_M`` mètres
       avant l'agent (au pire sur l'ensemble des agents). Mode ``"physique"``.
    2. Sinon, on applique le freinage proportionnel au niveau selon
       ``FREINAGE_PAR_NIVEAU``. Mode ``"proportionnel"``.
    3. Toute décélération est plafonnée à l'adhérence disponible ``µ·g``.
    4. Aucune accélération positive n'est jamais commandée : le moteur est une
       *couche de sécurité*, pas un contrôleur de conduite.

    La sortie inclut ``throttle`` et ``brake`` déjà normalisés dans ``[0, 1]``,
    directement consommables par un ``carla.VehicleControl``.

    Paramètres
    ----------
    assessment : RiskAssessment
        Résultat de ``assess_risk(ctx_courant)`` à cet instant.
    ctx : ScenarioContext
        Contexte courant, utilisé uniquement pour lire l'état de la route
        (adhérence µ·g).
    ego_x, ego_y : float
        Position de l'ego dans le repère monde.
    agents : Iterable[ObsAgent]
        Observations minimales des agents à cet instant.

    Retourne
    --------
    CommandeEgo : la commande à appliquer.
    """
    mu_g = modifiers.mu(ctx.etat_route) * metrics.G

    # 1. Freinage physique si conflit dans la voie devant.
    requis = 0.0
    for agent in agents:
        if _dans_la_voie_devant(agent.x, agent.y, ego_x, ego_y) and agent.drac > 0.0:
            d = math.hypot(agent.x - ego_x, agent.y - ego_y)
            d_sur = max(d - MARGE_ARRET_M, 0.5)
            # requis = v_fermeture² / (2·d_sur), obtenu par mise à l'échelle du DRAC
            requis = max(requis, agent.drac * d / d_sur)

    if requis > 0.0:
        accel = -min(requis, mu_g)
        mode = "physique"
    else:
        # 2. Sinon, freinage proportionnel au niveau.
        accel = max(FREINAGE_PAR_NIVEAU[assessment.level], -mu_g)
        mode = "nominal" if accel == 0.0 else "proportionnel"

    # 3. Traduction en throttle / brake normalisés [0, 1].
    if accel < 0.0:
        brake = min(-accel / mu_g, 1.0)
        throttle = 0.0
    else:
        brake = 0.0
        throttle = 0.0  # le moteur ne commande jamais d'accélération positive

    return CommandeEgo(
        acceleration_ms2=accel,
        throttle=throttle,
        brake=brake,
        mode=mode,
        mu_g=mu_g,
    )
