"""
Journal structuré — vérifier que la détection fait ce qu'on croit.

Deux flux distincts, deux fichiers :

- ``risques_*.csv`` — une ligne par **couple (ego, véhicule)** évalué, avec
  tout ce qui a mené au verdict : relation de voie, distance, vitesse
  relative, TTC, niveau. C'est le fichier qui permet de répondre à « pourquoi
  a-t-il dit CRITICAL ? » sans relancer la simulation.
- ``comportements_*.csv`` — une ligne par écart de conduite d'un véhicule
  autonome : lequel, quand, pourquoi, combien de temps.

Le premier sert à valider la logique de risque, le second à vérifier que
l'imprévisibilité reste plausible et rare.

Choix d'écriture
----------------
Journaliser **chaque couple à chaque tick** produirait des dizaines de milliers
de lignes par minute avec cinquante véhicules, pour l'essentiel identiques.
On n'écrit donc que ce qui apprend quelque chose : les couples dont le niveau
n'est pas SAFE, et les transitions de niveau. Le paramètre ``tout_journaliser``
permet de tout écrire quand on débogue un cas précis.
"""
from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, TextIO


@dataclass
class LigneRisque:
    """Une évaluation ego → véhicule, avec ses justifications."""
    t: float
    id_autre: int
    type_autre: str
    relation: str
    meme_voie: bool
    distance_m: float
    ecart_lateral_m: float
    cap_relatif_deg: float
    vitesse_ego_kmh: float
    vitesse_autre_kmh: float
    vitesse_relative_kmh: float
    ttc_s: Optional[float]
    thw_s: Optional[float]
    drac: float
    niveau: str
    metrique_decisive: str


class JournalSimulation:
    """Écrit les deux flux, et se ferme proprement.

    Utilisation :

        with JournalSimulation(Path("logs"), "dense", graine=42) as journal:
            ...
            journal.risque(ligne)
            journal.comportements(pilote.journal)
    """

    def __init__(self, dossier: Path, etiquette: str = "sim",
                 graine: Optional[int] = None, tout_journaliser: bool = False):
        dossier.mkdir(parents=True, exist_ok=True)
        horodatage = time.strftime("%Y%m%d_%H%M%S")
        suffixe = f"{etiquette}_{horodatage}"
        if graine is not None:
            suffixe = f"{etiquette}_g{graine}_{horodatage}"

        self.chemin_risques = dossier / f"risques_{suffixe}.csv"
        self.chemin_comportements = dossier / f"comportements_{suffixe}.csv"
        self.tout_journaliser = tout_journaliser

        self._f_risques: Optional[TextIO] = open(
            self.chemin_risques, "w", newline="", encoding="utf-8")
        self._w_risques = csv.writer(self._f_risques)
        self._w_risques.writerow([
            "t", "id_autre", "type_autre", "relation", "meme_voie",
            "distance_m", "ecart_lateral_m", "cap_relatif_deg",
            "vitesse_ego_kmh", "vitesse_autre_kmh", "vitesse_relative_kmh",
            "ttc_s", "thw_s", "drac", "niveau", "metrique_decisive",
        ])
        #: Dernier niveau connu par véhicule, pour ne journaliser que les
        #: transitions plutôt que la répétition du même état.
        self._dernier_niveau: Dict[int, str] = {}
        self._n_lignes = 0

        self._f_comportements: Optional[TextIO] = None

    # -- flux risque ------------------------------------------------------

    def risque(self, ligne: LigneRisque) -> bool:
        """Journalise une évaluation si elle apprend quelque chose.

        Renvoie True si la ligne a été écrite.
        """
        if self._f_risques is None:
            return False
        precedent = self._dernier_niveau.get(ligne.id_autre)
        interessant = (
            self.tout_journaliser
            or ligne.niveau != "SAFE"
            or (precedent is not None and precedent != ligne.niveau)
        )
        self._dernier_niveau[ligne.id_autre] = ligne.niveau
        if not interessant:
            return False

        self._w_risques.writerow([
            f"{ligne.t:.2f}", ligne.id_autre, ligne.type_autre, ligne.relation,
            "oui" if ligne.meme_voie else "non",
            f"{ligne.distance_m:.1f}", f"{ligne.ecart_lateral_m:+.2f}",
            f"{ligne.cap_relatif_deg:+.1f}",
            f"{ligne.vitesse_ego_kmh:.1f}", f"{ligne.vitesse_autre_kmh:.1f}",
            f"{ligne.vitesse_relative_kmh:+.1f}",
            f"{ligne.ttc_s:.2f}" if ligne.ttc_s is not None else "",
            f"{ligne.thw_s:.2f}" if ligne.thw_s is not None else "",
            f"{ligne.drac:.2f}", ligne.niveau, ligne.metrique_decisive,
        ])
        self._n_lignes += 1
        return True

    # -- flux comportements -----------------------------------------------

    def comportements(self, evenements) -> None:
        """Écrit d'un bloc le journal des écarts de conduite."""
        if not evenements:
            return
        self._f_comportements = open(
            self.chemin_comportements, "w", newline="", encoding="utf-8")
        w = csv.writer(self._f_comportements)
        w.writerow(["t", "id_vehicule", "comportement", "profil",
                    "duree_s", "contexte"])
        for e in evenements:
            w.writerow([f"{e.t:.2f}", e.id_vehicule, e.comportement.value,
                        e.profil, f"{e.duree_s:.1f}", e.contexte])

    # -- cycle de vie -----------------------------------------------------

    @property
    def n_lignes_risque(self) -> int:
        return self._n_lignes

    def fermer(self) -> None:
        for f in (self._f_risques, self._f_comportements):
            if f is not None:
                f.close()
        self._f_risques = None
        self._f_comportements = None

    def __enter__(self) -> "JournalSimulation":
        return self

    def __exit__(self, *exc) -> None:
        self.fermer()
