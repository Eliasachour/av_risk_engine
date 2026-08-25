"""
Évaluation du moteur contre les scénarios de référence.

Pour chaque scénario, on compare le niveau PRÉDIT par le moteur au niveau
ATTENDU (vérité terrain). On distingue, dans l'esprit de la sécurité :
  - sous-classement (prédit < attendu)  = DÉTECTION MANQUÉE   (le plus grave)
  - surclassement   (prédit > attendu)  = fausse alarme
Le résultat est une matrice de confusion + des compteurs synthétiques, base de
toute calibration des seuils de RiskConfig.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from risk_engine import RiskConfig, RiskLevel, assess_risk

from .scenarios_ref import REFERENCES, CasReference

_ABBR = {RiskLevel.SAFE: "S", RiskLevel.WATCH: "W", RiskLevel.DANGER: "D", RiskLevel.CRITICAL: "C"}


@dataclass
class Resultat:
    cas: CasReference
    predit: RiskLevel
    declencheur: str

    @property
    def attendu(self) -> RiskLevel:
        return self.cas.niveau_attendu

    @property
    def ecart(self) -> int:
        return int(self.predit) - int(self.attendu)

    @property
    def statut(self) -> str:
        if self.ecart == 0:
            return "OK"
        return "surclassé (f. alarme)" if self.ecart > 0 else "SOUS-CLASSÉ (manqué)"


def evaluer(cfg: Optional[RiskConfig] = None,
            references: List[CasReference] = REFERENCES) -> List[Resultat]:
    cfg = cfg or RiskConfig()
    res = []
    for cas in references:
        a = assess_risk(cas.ctx, cfg)
        decl = "—"
        if a.details:
            pire = max(a.details, key=lambda d: d.level)
            decl = pire.metrique_decisive
        res.append(Resultat(cas, a.level, decl))
    return res


def matrice_confusion(res: List[Resultat]) -> Dict[RiskLevel, Dict[RiskLevel, int]]:
    """Lignes = niveau attendu, colonnes = niveau prédit."""
    niveaux = list(RiskLevel)
    M = {a: {p: 0 for p in niveaux} for a in niveaux}
    for r in res:
        M[r.attendu][r.predit] += 1
    return M


def synthese(res: List[Resultat]) -> Dict[str, float]:
    n = len(res)
    corrects = sum(1 for r in res if r.ecart == 0)
    sur = sum(1 for r in res if r.ecart > 0)
    sous = sum(1 for r in res if r.ecart < 0)
    return {
        "n": n,
        "corrects": corrects,
        "surclassements": sur,        # fausses alarmes
        "sous_classements": sous,     # détections manquées
        "exactitude": corrects / n if n else 0.0,
    }


# ---------- mise en forme ----------

def format_rapport(res: List[Resultat]) -> str:
    lignes = []
    entete = f"{'ID':<6} {'Scénario':<24} {'attendu':<9} {'prédit':<9} {'déclencheur':<14} statut"
    lignes.append(entete)
    lignes.append("-" * len(entete))
    for r in res:
        lignes.append(
            f"{r.cas.id:<6} {r.cas.nom:<24} {str(r.attendu):<9} {str(r.predit):<9} "
            f"{r.declencheur:<14} {r.statut}"
        )

    # matrice de confusion
    M = matrice_confusion(res)
    niveaux = list(RiskLevel)
    lignes.append("")
    lignes.append("Matrice de confusion (lignes = attendu, colonnes = prédit) :")
    lignes.append("           " + "  ".join(f"{_ABBR[p]:>2}" for p in niveaux))
    for a in niveaux:
        row = "  ".join(f"{M[a][p]:>2}" for p in niveaux)
        lignes.append(f"  {str(a):<8} {row}")
    lignes.append("  (S=SAFE  W=WATCH  D=DANGER  C=CRITICAL ; diagonale = correct)")

    # synthèse
    s = synthese(res)
    lignes.append("")
    lignes.append(
        f"Exactitude : {s['corrects']}/{s['n']} ({100*s['exactitude']:.0f} %)  |  "
        f"détections manquées : {s['sous_classements']}  |  "
        f"fausses alarmes : {s['surclassements']}"
    )
    if s["sous_classements"]:
        manques = ", ".join(r.cas.id for r in res if r.ecart < 0)
        lignes.append(f"  ⚠ sous-classements (à corriger en priorité) : {manques}")
    return "\n".join(lignes)
