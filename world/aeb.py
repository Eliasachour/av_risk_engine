"""
Assistance conducteur — évaluation, alerte, AEB.

Trois niveaux d'ambition, sélectionnables au démarrage :

- ``"eval"``  : le moteur observe et affiche, aucune intervention.
- ``"alerte"`` : idem + alerte visuelle/sonore en DANGER et CRITICAL.
- ``"aeb"``   : idem + reprise automatique du frein si CRITICAL persiste
                (Automatic Emergency Braking). Le conducteur peut reprendre
                la main en relâchant puis en réappuyant sur l'accélérateur.

Cette machine à états est délibérément **stateful** (persistante entre les
ticks) parce que l'AEB doit décider en tenant compte de l'historique — un
CRITICAL d'un seul tick sur un artefact de perception ne doit pas déclencher
un freinage d'urgence, il faut une persistance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from risk_engine import RiskLevel


@dataclass
class DecisionAssistance:
    """Ce que l'assistance décide à cet instant."""
    override_brake: bool = False       # vrai si l'AEB reprend le frein
    override_brake_valeur: float = 0.0  # ∈ [0, 1]
    alerte_active: bool = False        # vrai si on est en DANGER ou CRITICAL
    alerte_critical: bool = False      # vrai si CRITICAL (pour pulsation)
    message: str = ""                  # message court pour le HUD


class Assistance:
    """Machine à états de l'assistance conducteur.

    Paramètres
    ----------
    mode : str
        "eval" | "alerte" | "aeb"
    duree_critical_avant_aeb : float
        Combien de secondes de CRITICAL persistant avant de déclencher l'AEB.
        Trop court → faux positifs ; trop long → freine trop tard. 0.4 s est
        un bon compromis (2 ticks à 20 Hz + marge).
    duree_alerte_min : float
        Durée minimale d'une alerte une fois déclenchée, même si le niveau
        redescend — évite le clignotement quand on flotte au seuil.
    """

    def __init__(self, mode: str = "alerte",
                 duree_critical_avant_aeb: float = 0.4,
                 duree_alerte_min: float = 1.0):
        assert mode in ("eval", "alerte", "aeb"), f"Mode inconnu : {mode}"
        self.mode = mode
        self.duree_critical_avant_aeb = duree_critical_avant_aeb
        self.duree_alerte_min = duree_alerte_min

        self._t_critical_debut: Optional[float] = None
        self._t_derniere_alerte: float = -1e9
        self._aeb_verrouille: bool = False       # AEB engagé, reste engagé
        self._t_aeb_debut: Optional[float] = None

    def decider(self, niveau: RiskLevel, t_sim: float,
                conducteur_freine: bool = False,
                conducteur_accelere: bool = False) -> DecisionAssistance:
        """Décide de l'action d'assistance à cet instant.

        Parameters
        ----------
        niveau : RiskLevel
            Verdict global du moteur à ce tick.
        t_sim : float
            Temps simulé (s).
        conducteur_freine : bool
            Vrai si le conducteur freine déjà (utile : ne pas doubler l'AEB
            si l'humain gère déjà).
        conducteur_accelere : bool
            Vrai si le conducteur appuie sur l'accélérateur — signal explicite
            de reprise de contrôle qui désengage l'AEB.
        """
        d = DecisionAssistance()

        # 1. Suivi du CRITICAL persistant
        if niveau == RiskLevel.CRITICAL:
            if self._t_critical_debut is None:
                self._t_critical_debut = t_sim
        else:
            self._t_critical_debut = None

        # 2. Alerte visuelle (modes "alerte" et "aeb")
        if self.mode in ("alerte", "aeb"):
            if int(niveau) >= int(RiskLevel.DANGER):
                self._t_derniere_alerte = t_sim
            if t_sim - self._t_derniere_alerte < self.duree_alerte_min:
                d.alerte_active = True
                d.alerte_critical = (niveau == RiskLevel.CRITICAL)
                if niveau == RiskLevel.CRITICAL:
                    d.message = "DANGER IMMINENT — freinez"
                else:
                    d.message = "Attention — situation dégradée"

        # 3. AEB (mode "aeb" seulement)
        if self.mode == "aeb":
            if not self._aeb_verrouille:
                # Déclenchement : CRITICAL persistant + conducteur passif
                if (self._t_critical_debut is not None
                        and t_sim - self._t_critical_debut >= self.duree_critical_avant_aeb
                        and not conducteur_freine):
                    self._aeb_verrouille = True
                    self._t_aeb_debut = t_sim
                    d.message = "AEB ENGAGÉ"
            else:
                # Verrouillé : rester engagé tant que le conducteur ne reprend pas
                if conducteur_accelere:
                    # Reprise explicite
                    self._aeb_verrouille = False
                    self._t_aeb_debut = None
                    d.message = "Contrôle rendu au conducteur"
                elif niveau == RiskLevel.SAFE and (t_sim - (self._t_aeb_debut or 0)) > 2.0:
                    # Danger passé et déjà 2s en AEB → désengager doucement
                    self._aeb_verrouille = False
                    self._t_aeb_debut = None

            if self._aeb_verrouille:
                d.override_brake = True
                d.override_brake_valeur = 1.0
                d.message = d.message or "AEB actif"

        return d

    def statut_court(self) -> str:
        """Petit label pour le HUD (« EVAL » / « ALERTE » / « AEB »)."""
        return {
            "eval": "EVAL",
            "alerte": "ALERTE",
            "aeb": "AEB",
        }[self.mode]
