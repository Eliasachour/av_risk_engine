"""
Visualisation détaillée de l'évolution temporelle du risque (matplotlib).

- plot_metrics    : 5 panneaux légendés — distances (réelle vs RSS), métriques
                    temporelles (TTC, THW), décélération (DRAC vs disponible),
                    VITESSE DE L'EGO avec zones de freinage, et niveau de risque.
- plot_comparaison: distance ego-agent avec vs sans réaction de l'ego.
- animate_topdown : vue de dessus animée (agents colorés, vitesse ego + freinage).

matplotlib est optionnel (pip install matplotlib). Les figures sont TOUJOURS
enregistrées en image puis renvoyées (chemin) : on utilise un backend non
interactif (Agg), ce qui évite les crashs d'ouverture de fenêtre GUI sur macOS.
C'est l'appelant (simulate.py) qui ouvre les images avec l'app du système.
"""
from __future__ import annotations

import math
import os
import tempfile
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")  # backend non interactif : pas de fenêtre GUI -> pas de crash
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

from risk_engine import RiskLevel, TypeAgent, metrics, modifiers
from risk_engine.context import ScenarioContext
from sim.kinematic import Frame


def _chemin_sortie(prefixe: str, ext: str, save_path: Optional[str]) -> str:
    """Renvoie save_path s'il est fourni, sinon un fichier temporaire nommé."""
    if save_path:
        return save_path
    fd, chemin = tempfile.mkstemp(prefix=f"{prefixe}_", suffix=ext)
    os.close(fd)
    return chemin

COULEURS = {
    RiskLevel.SAFE: "#2e7d32",
    RiskLevel.WATCH: "#f9a825",
    RiskLevel.DANGER: "#ef6c00",
    RiskLevel.CRITICAL: "#c62828",
}


def _distance(f: Frame) -> float:
    return min((math.hypot(s.x - f.ego.x, s.y - f.ego.y) for s in f.agents), default=math.inf)


def _critique(f: Frame):
    if not f.assessment.details:
        return None
    return max(f.assessment.details, key=lambda d: d.level)


def _plafond(x: float, hi: float = 10.0) -> float:
    return min(x, hi) if math.isfinite(x) else hi


def _shade_freinage(ax, t, freine, dt, label="Freinage de l'ego"):
    deja = False
    for ti, b in zip(t, freine):
        if b:
            ax.axvspan(ti, ti + dt, color="#c62828", alpha=0.12, lw=0,
                       label=(label if not deja else None))
            deja = True


def plot_metrics(frames: List[Frame], ctx: ScenarioContext,
                 titre: str = "Simulation du risque", reaction: bool = False,
                 save_path: Optional[str] = None, agent_index: Optional[int] = None):
    t = [f.t for f in frames]
    v_ego = [f.ego.speed_ms * 3.6 for f in frames]
    freine = [f.ego_accel < 0 for f in frames]
    niveaux = [int(f.assessment.level) for f in frames]
    a_dispo = modifiers.mu(ctx.etat_route) * metrics.G
    dt = (t[1] - t[0]) if len(t) > 1 else 0.1

    n_agents = len(ctx.agents)
    indices = [agent_index] if agent_index is not None else list(range(n_agents))
    _PALETTE = ["#1565c0", "#6a1b9a", "#00838f", "#ef6c00", "#ad1457", "#558b2f"]

    def _col(i):
        return _PALETTE[i % len(_PALETTE)]

    def _nom(i):
        return f"{ctx.agents[i].type_agent.value} #{i + 1}"

    def _det(f, i):
        return f.assessment.details[i] if i < len(f.assessment.details) else None

    fig, (ax0, ax1, ax2, ax3, ax4) = plt.subplots(5, 1, figsize=(10, 13), sharex=True)
    sel_txt = _nom(agent_index) if agent_index is not None else f"{n_agents} agent(s)"
    mode = "ego freine selon le risque" if reaction else "ego SANS réaction"
    fig.suptitle(
        f"{titre}  —  {mode}\n"
        f"ego {ctx.vitesse_ego_kmh:.0f} km/h · {ctx.meteo.value}/{ctx.etat_route.value}"
        f" · {sel_txt}",
        fontsize=13, fontweight="bold",
    )

    # 1) Distances : réelle (solide) et RSS (pointillé), une couleur par agent
    for i in indices:
        d_i = [math.hypot(f.agents[i].x - f.ego.x, f.agents[i].y - f.ego.y)
               if i < len(f.agents) else math.nan for f in frames]
        rss_i = [_det(f, i).rss_min if _det(f, i) else math.nan for f in frames]
        ax0.plot(t, d_i, color=_col(i), lw=1.6, label=f"Distance — {_nom(i)}")
        ax0.plot(t, rss_i, color=_col(i), ls="--", lw=1.0, alpha=0.6, label=f"RSS — {_nom(i)}")
    ax0.axhline(1.5, color="black", ls=":", lw=0.8, label="Seuil de collision")
    ax0.set_ylabel("Distance (m)")
    ax0.set_title("Distance réelle vs distance de sécurité RSS", fontsize=10)
    ax0.legend(fontsize=8, loc="upper right", ncol=max(1, len(indices)))
    ax0.grid(alpha=0.3)

    # 2) Métriques temporelles : TTC (solide) et THW (pointillé), par agent
    for i in indices:
        ttc_i = [_plafond(_det(f, i).ttc) if _det(f, i) else math.nan for f in frames]
        thw_i = [_plafond(_det(f, i).thw) if _det(f, i) else math.nan for f in frames]
        ax1.plot(t, ttc_i, color=_col(i), lw=1.6, label=f"TTC — {_nom(i)}")
        ax1.plot(t, thw_i, color=_col(i), ls=":", lw=1.2, alpha=0.6, label=f"THW — {_nom(i)}")
    ax1.axhline(4.0, color="#2e7d32", ls="--", lw=0.8, label="Seuil SAFE (4 s)")
    ax1.axhline(1.5, color="#c62828", ls="--", lw=0.8, label="Seuil DANGER (1,5 s)")
    ax1.set_ylabel("Temps (s)")
    ax1.set_ylim(0, 10.5)
    ax1.set_title("Métriques temporelles (plafonnées à 10 s)", fontsize=10)
    ax1.legend(fontsize=8, loc="upper right", ncol=2)
    ax1.grid(alpha=0.3)

    # 3) Décélération requise (DRAC) par agent vs disponible
    for i in indices:
        drac_i = [_det(f, i).drac if _det(f, i) else 0.0 for f in frames]
        ax2.plot(t, drac_i, color=_col(i), lw=1.6, label=f"DRAC — {_nom(i)}")
    ax2.axhline(a_dispo, color="#283593", ls="--", lw=1.0,
                label=f"Décélération disponible µ·g = {a_dispo:.1f} m/s²")
    ax2.set_ylabel("Décél. (m/s²)")
    ax2.set_title("Décélération requise vs disponible (au-delà = collision inévitable)", fontsize=10)
    ax2.legend(fontsize=8, loc="upper right")
    ax2.grid(alpha=0.3)

    # 4) Vitesse de l'ego + zones de freinage
    ax3.plot(t, v_ego, color="#1565c0", lw=1.8, label="Vitesse de l'ego")
    _shade_freinage(ax3, t, freine, dt)
    ax3.set_ylabel("Vitesse ego (km/h)")
    ax3.set_ylim(0, max(v_ego) * 1.15 + 1)
    ax3.set_title("Vitesse de l'ego — les bandes rouges indiquent le freinage", fontsize=10)
    ax3.legend(fontsize=8, loc="upper right")
    ax3.grid(alpha=0.3)

    # 5) Niveau de risque
    ax4.step(t, niveaux, where="post", color="black", lw=1.2)
    for f, ti in zip(frames, t):
        ax4.axvspan(ti, ti + dt, color=COULEURS[f.assessment.level], alpha=0.25, lw=0)
    ax4.set_yticks([0, 1, 2, 3])
    ax4.set_yticklabels(["SAFE", "WATCH", "DANGER", "CRITICAL"])
    ax4.set_ylabel("Niveau")
    ax4.set_xlabel("Temps (s)")
    ax4.set_title("Niveau de risque évalué", fontsize=10)
    ax4.grid(alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    chemin = _chemin_sortie("metrics", ".png", save_path)
    fig.savefig(chemin, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return chemin


def plot_comparaison(frames_sans: List[Frame], frames_avec: List[Frame],
                     save_path: Optional[str] = None):
    fig, (axd, axv) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    fig.suptitle("Effet de la couche de sécurité (avec vs sans réaction)", fontweight="bold")

    axd.plot([f.t for f in frames_sans], [_distance(f) for f in frames_sans],
             color="#c62828", lw=1.6, label="sans réaction")
    axd.plot([f.t for f in frames_avec], [_distance(f) for f in frames_avec],
             color="#2e7d32", lw=1.6, label="avec freinage")
    axd.axhline(1.5, ls="--", c="black", lw=0.8, label="seuil de collision")
    axd.set_ylabel("Distance ego–agent (m)")
    axd.legend()
    axd.grid(alpha=0.3)

    axv.plot([f.t for f in frames_sans], [f.ego.speed_ms * 3.6 for f in frames_sans],
             color="#c62828", lw=1.6, label="sans réaction")
    axv.plot([f.t for f in frames_avec], [f.ego.speed_ms * 3.6 for f in frames_avec],
             color="#2e7d32", lw=1.6, label="avec freinage")
    axv.set_xlabel("Temps (s)")
    axv.set_ylabel("Vitesse ego (km/h)")
    axv.legend()
    axv.grid(alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    chemin = _chemin_sortie("comparaison", ".png", save_path)
    fig.savefig(chemin, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return chemin


def animate_topdown(frames: List[Frame], ctx: ScenarioContext,
                    save_path: Optional[str] = None, fps: int = 10, pas: int = 2,
                    repere_absolu: bool = False):
    """Vue de dessus animée, colorée par niveau de risque.

    Deux repères possibles :
      - lié à l'ego (défaut) : l'ego est fixe au centre, les agents se rapprochent ;
      - absolu / monde (`repere_absolu=True`) : positions réelles, l'ego avance —
        un piéton qui traverse apparaît alors perpendiculairement, sans l'effet
        de dérive dû au mouvement de l'ego.
    """
    seq = frames[::pas]

    def pos(state, f):
        return (state.x, state.y) if repere_absolu else (state.x - f.ego.x, state.y - f.ego.y)

    # Cadrage englobant l'ego (si repère absolu) et tous les agents sur la séquence.
    pts = []
    for f in seq:
        if repere_absolu:
            pts.append((f.ego.x, f.ego.y))
        pts.extend(pos(s, f) for s in f.agents)
    pts = pts or [(0.0, 0.0)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x_hi, x_lo = max(max(xs), 10.0) + 6, min(min(xs), 0.0) - 6
    y_hi, y_lo = max(max(ys), 4.0) + 2, min(min(ys), -4.0) - 2

    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.set_aspect("equal")
    ax.set_xlabel("Distance longitudinale (m)")
    ax.set_ylabel("Écart latéral (m)")
    titre = "repère absolu (monde)" if repere_absolu else "repère lié à l'ego"
    ax.set_title(f"Vue de dessus — {titre}", fontweight="bold")
    for ly in (-1.75, 1.75):
        ax.axhline(ly, color="gray", ls="--", lw=0.6, alpha=0.6)

    ego_marker, = ax.plot([0], [0], marker=">", markersize=16, color="#1565c0", zorder=5)
    # Un marqueur par type d'agent (la couleur, elle, encode le niveau de risque).
    MARKERS = {TypeAgent.VOITURE: "s", TypeAgent.CAMION: "P", TypeAgent.CYCLISTE: "D",
               TypeAgent.PIETON: "o", TypeAgent.OUVRIER: "X"}
    arts = []
    for i, ag in enumerate(ctx.agents):
        art = ax.scatter([], [], s=170, marker=MARKERS.get(ag.type_agent, "o"),
                         facecolor="lightgray", edgecolors="black", linewidths=0.6,
                         zorder=6, label=f"{ag.type_agent.value} #{i + 1}")
        arts.append(art)
    if ctx.agents:
        ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    txt = ax.text(0.02, 0.95, "", transform=ax.transAxes, fontsize=10, va="top", fontweight="bold")
    ego_txt = ax.text(0.02, 0.06, "", transform=ax.transAxes, fontsize=9, color="#1565c0")

    def update(i):
        f = seq[i]
        ex, ey = pos(f.ego, f)
        ego_marker.set_data([ex], [ey])
        for j, art in enumerate(arts):
            if j < len(f.agents):
                art.set_offsets([list(pos(f.agents[j], f))])
                art.set_facecolor(COULEURS[f.assessment.details[j].level])
        freine = f.ego_accel < 0
        ego_marker.set_color("#c62828" if freine else "#1565c0")
        txt.set_text(f"t = {f.t:4.1f} s    niveau : {f.assessment.level}")
        txt.set_color(COULEURS[f.assessment.level])
        ego_txt.set_text(f"ego : {f.ego.speed_ms * 3.6:4.0f} km/h"
                         + ("   — FREINAGE" if freine else ""))
        return (*arts, txt, ego_txt, ego_marker)

    anim = FuncAnimation(fig, update, frames=len(seq), interval=1000 / fps, blit=False)
    chemin = _chemin_sortie("topdown", ".gif", save_path)
    anim.save(chemin, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return chemin
