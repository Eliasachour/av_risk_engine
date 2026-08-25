"""
Formulaire de saisie d'un scénario (tkinter).

Au lancement, une fenêtre demande les variables du scénario. Les menus se
filtrent dynamiquement pour rester cohérents (météo -> état de route -> visibilité,
type de route + zone de travaux -> limites). À la validation, un ScenarioContext
est construit, ou les incohérences restantes sont signalées.

tkinter est inclus dans Python standard ; aucune installation requise.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import messagebox, ttk

from risk_engine import ScenarioContext, format_seuils, tableau_metriques
from risk_engine.context import (
    Agent,
    EtatRoute,
    Geometrie,
    Heure,
    Meteo,
    TypeAgent,
    TypeRoute,
)
from risk_engine.report import lignes_tableau, _COLS
from scenarios import constraints


def _valeurs(enum_cls) -> List[str]:
    return [e.value for e in enum_cls]


def _depuis_valeur(enum_cls, valeur: str):
    return enum_cls(valeur)


class ScenarioForm:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.result: Optional[ScenarioContext] = None
        self.reaction: bool = False
        self.agents: List[Agent] = []
        master.title("Configuration du scénario")
        self._build()

    # ---------- construction de l'interface ----------
    def _build(self) -> None:
        pad = {"padx": 6, "pady": 4}

        # ===== Paramètres routiers =====
        f_route = ttk.LabelFrame(self.master, text="Paramètres routiers")
        f_route.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        ttk.Label(f_route, text="Type de route").grid(row=0, column=0, sticky="w", **pad)
        self.cb_type_route = ttk.Combobox(f_route, values=_valeurs(TypeRoute), state="readonly")
        self.cb_type_route.set(TypeRoute.NATIONALE.value)
        self.cb_type_route.grid(row=0, column=1, **pad)
        self.cb_type_route.bind("<<ComboboxSelected>>", lambda e: self._maj_limites())
        ttk.Label(f_route, text="Géométrie").grid(row=1, column=0, sticky="w", **pad)
        self.cb_geometrie = ttk.Combobox(f_route, values=_valeurs(Geometrie), state="readonly")
        self.cb_geometrie.set(Geometrie.DROITE.value)
        self.cb_geometrie.grid(row=1, column=1, **pad)
        self.var_zone = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_route, text="Zone de travaux", variable=self.var_zone,
                        command=self._maj_limites).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(f_route, text="Limite (km/h)").grid(row=3, column=0, sticky="w", **pad)
        self.cb_limite = ttk.Combobox(f_route, state="readonly")
        self.cb_limite.grid(row=3, column=1, **pad)

        # ===== Paramètres environnementaux =====
        f_env = ttk.LabelFrame(self.master, text="Paramètres environnementaux")
        f_env.grid(row=1, column=0, sticky="ew", padx=8, pady=6)
        ttk.Label(f_env, text="Météo").grid(row=0, column=0, sticky="w", **pad)
        self.cb_meteo = ttk.Combobox(f_env, values=_valeurs(Meteo), state="readonly")
        self.cb_meteo.set(Meteo.CLAIR.value)
        self.cb_meteo.grid(row=0, column=1, **pad)
        self.cb_meteo.bind("<<ComboboxSelected>>", lambda e: self._maj_meteo())
        ttk.Label(f_env, text="État de route").grid(row=1, column=0, sticky="w", **pad)
        self.cb_etat = ttk.Combobox(f_env, state="readonly")
        self.cb_etat.grid(row=1, column=1, **pad)
        ttk.Label(f_env, text="Heure").grid(row=2, column=0, sticky="w", **pad)
        self.cb_heure = ttk.Combobox(f_env, values=_valeurs(Heure), state="readonly")
        self.cb_heure.set(Heure.JOUR.value)
        self.cb_heure.grid(row=2, column=1, **pad)
        self.cb_heure.bind("<<ComboboxSelected>>", lambda e: self._maj_meteo())
        ttk.Label(f_env, text="Visibilité (m)").grid(row=3, column=0, sticky="w", **pad)
        self.var_vis = tk.DoubleVar(value=400.0)
        self.sp_vis = ttk.Spinbox(f_env, from_=5, to=500, increment=10, textvariable=self.var_vis)
        self.sp_vis.grid(row=3, column=1, **pad)
        self.lbl_vis = ttk.Label(f_env, text="")
        self.lbl_vis.grid(row=3, column=2, sticky="w", **pad)

        # ===== Véhicule ego =====
        f_ego = ttk.LabelFrame(self.master, text="Véhicule ego")
        f_ego.grid(row=2, column=0, sticky="ew", padx=8, pady=6)
        ttk.Label(f_ego, text="Vitesse ego (km/h)").grid(row=0, column=0, sticky="w", **pad)
        self.var_ego = tk.DoubleVar(value=80.0)
        ttk.Spinbox(f_ego, from_=0, to=160, increment=5, textvariable=self.var_ego).grid(
            row=0, column=1, **pad)
        self.var_reaction = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_ego, text="L'ego freine en cas de danger (sinon : aucune réaction)",
                        variable=self.var_reaction).grid(row=1, column=0, columnspan=3, sticky="w", **pad)

        # ===== Usagers (humains et autres agents) =====
        f_ag = ttk.LabelFrame(self.master, text="Usagers (humains et autres agents)")
        f_ag.grid(row=3, column=0, sticky="ew", padx=8, pady=6)
        af = ttk.Frame(f_ag)
        af.grid(row=0, column=0, sticky="w", **pad)
        ttk.Label(af, text="Type").grid(row=0, column=0)
        self.cb_ag_type = ttk.Combobox(af, values=_valeurs(TypeAgent), state="readonly", width=10)
        self.cb_ag_type.set(TypeAgent.VOITURE.value)
        self.cb_ag_type.grid(row=1, column=0, padx=3)
        ttk.Label(af, text="V (km/h)").grid(row=0, column=1)
        self.var_ag_v = tk.DoubleVar(value=30.0)
        ttk.Spinbox(af, from_=0, to=200, increment=5, width=7, textvariable=self.var_ag_v).grid(row=1, column=1, padx=3)
        ttk.Label(af, text="Dist (m)").grid(row=0, column=2)
        self.var_ag_d = tk.DoubleVar(value=40.0)
        ttk.Spinbox(af, from_=0, to=500, increment=5, width=7, textvariable=self.var_ag_d).grid(row=1, column=2, padx=3)
        ttk.Label(af, text="Cap (°)").grid(row=0, column=3)
        self.var_ag_cap = tk.DoubleVar(value=0.0)
        ttk.Spinbox(af, from_=0, to=359, increment=5, width=6, textvariable=self.var_ag_cap).grid(row=1, column=3, padx=3)
        ttk.Label(af, text="Accél").grid(row=0, column=4)
        self.var_ag_a = tk.DoubleVar(value=0.0)
        ttk.Spinbox(af, from_=-9, to=4, increment=0.5, width=6, textvariable=self.var_ag_a).grid(row=1, column=4, padx=3)
        ttk.Label(af, text="Écart lat.").grid(row=0, column=5)
        self.var_ag_ecart = tk.DoubleVar(value=0.0)
        ttk.Spinbox(af, from_=-20, to=20, increment=0.5, width=6, textvariable=self.var_ag_ecart).grid(row=1, column=5, padx=3)
        self.var_ag_mes = tk.BooleanVar(value=True)
        ttk.Checkbutton(af, text="profondeur mesurée", variable=self.var_ag_mes).grid(row=1, column=6, padx=3)
        ttk.Button(af, text="Ajouter", command=self._ajouter_agent).grid(row=1, column=7, padx=6)
        self.lst_agents = tk.Listbox(f_ag, height=4, width=60)
        self.lst_agents.grid(row=1, column=0, sticky="w", **pad)
        ttk.Button(f_ag, text="Supprimer l'agent sélectionné", command=self._supprimer_agent).grid(
            row=2, column=0, sticky="w", **pad)

        # ===== Lancer =====
        boutons = ttk.Frame(self.master)
        boutons.grid(row=4, column=0, pady=10)
        ttk.Button(boutons, text="Calculer les métriques", command=self._afficher_metriques).grid(
            row=0, column=0, padx=6)
        ttk.Button(boutons, text="Lancer la simulation", command=self._lancer).grid(
            row=0, column=1, padx=6)

        # initialisation des champs filtrés
        self._maj_meteo()
        self._maj_limites()

    # ---------- filtrage dynamique (cohérence) ----------
    def _maj_meteo(self) -> None:
        meteo = _depuis_valeur(Meteo, self.cb_meteo.get())
        heure = _depuis_valeur(Heure, self.cb_heure.get())
        etats = [e.value for e in constraints.etats_route_compatibles(meteo)]
        self.cb_etat.configure(values=etats)
        if self.cb_etat.get() not in etats:
            self.cb_etat.set(etats[0])
        vmin, vmax = constraints.plage_visibilite(meteo, heure)
        self.sp_vis.configure(from_=max(5, vmin * 0.5), to=vmax)
        self.var_vis.set(round((vmin + vmax) / 2.0))
        self.lbl_vis.configure(text=f"plage ~ {vmin:.0f}–{vmax:.0f} m")

    def _maj_limites(self) -> None:
        tr = _depuis_valeur(TypeRoute, self.cb_type_route.get())
        limites = [str(v) for v in constraints.limites_compatibles(tr, self.var_zone.get())]
        self.cb_limite.configure(values=limites)
        if self.cb_limite.get() not in limites:
            self.cb_limite.set(limites[-1])

    # ---------- agents ----------
    def _ajouter_agent(self) -> None:
        ag = Agent(
            type_agent=_depuis_valeur(TypeAgent, self.cb_ag_type.get()),
            vitesse_kmh=float(self.var_ag_v.get()),
            distance_m=float(self.var_ag_d.get()),
            cap_relatif_deg=float(self.var_ag_cap.get()),
            acceleration_ms2=float(self.var_ag_a.get()),
            profondeur_mesuree=bool(self.var_ag_mes.get()),
            ecart_lateral_m=float(self.var_ag_ecart.get()),
        )
        self.agents.append(ag)
        self.lst_agents.insert(
            tk.END,
            f"{ag.type_agent.value} | v={ag.vitesse_kmh:.0f} | d={ag.distance_m:.0f}m | "
            f"cap={ag.cap_relatif_deg:.0f}° | a={ag.acceleration_ms2:.1f} | "
            f"écart={ag.ecart_lateral_m:.1f}m | "
            f"{'mesurée' if ag.profondeur_mesuree else 'inférée'}",
        )

    def _supprimer_agent(self) -> None:
        sel = self.lst_agents.curselection()
        if sel:
            i = sel[0]
            self.lst_agents.delete(i)
            del self.agents[i]

    # ---------- validation & sortie ----------
    def _afficher_metriques(self) -> None:
        """Ouvre une fenêtre : récapitulatif de TOUS les paramètres + table des métriques."""
        ctx = self._construire_contexte()
        problemes = constraints.valider(ctx)
        if problemes:
            messagebox.showerror("Scénario incohérent", "\n".join("• " + p for p in problemes))
            return

        win = tk.Toplevel(self.master)
        win.title("Métriques du scénario")
        pad = {"padx": 8, "pady": 3}

        # 1) Récapitulatif de tous les paramètres du contexte
        ttk.Label(win, text="Paramètres du scénario", font=("", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", **pad
        )
        recap = [
            ("Type de route", ctx.type_route.value),
            ("Géométrie", ctx.geometrie.value),
            ("Zone de travaux", "oui" if ctx.zone_travaux else "non"),
            ("Limite (km/h)", f"{ctx.limite_vitesse_kmh:.0f}"),
            ("État de route", ctx.etat_route.value),
            ("Météo", ctx.meteo.value),
            ("Heure", ctx.heure.value),
            ("Visibilité (m)", f"{ctx.visibilite_m:.0f}"),
            ("Vitesse ego (km/h)", f"{ctx.vitesse_ego_kmh:.0f}"),
            ("Nombre d'agents", str(len(ctx.agents))),
        ]
        r = 1
        for nom, val in recap:
            ttk.Label(win, text=nom).grid(row=r, column=0, sticky="w", **pad)
            ttk.Label(win, text=val).grid(row=r, column=1, sticky="w", **pad)
            r += 1

        # 2) Table des métriques par agent
        ttk.Separator(win, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=6
        )
        r += 1
        ttk.Label(win, text="Métriques par agent", font=("", 10, "bold")).grid(
            row=r, column=0, columnspan=2, sticky="w", **pad
        )
        r += 1

        if not ctx.agents:
            ttk.Label(win, text="(aucun agent : ajoute au moins un agent)").grid(
                row=r, column=0, columnspan=2, sticky="w", **pad
            )
            return

        table = tableau_metriques(ctx)
        noms_cols = [nom for nom, _ in _COLS]
        col_metrique = {"TTC(s)": "TTC", "THW(s)": "THW", "PET(s)": "PET",
                        "RSS(m)": "RSS", "CI": "CI", "DRAC": "DRAC"}
        couleurs = {
            "SAFE": ("#d7f2df", "#1b5e20"), "WATCH": ("#fdf0c8", "#6d5200"),
            "DANGER": ("#ffe0b2", "#7a3d00"), "CRITICAL": ("#ffcdd2", "#8a1c1c"),
        }
        tbl = tk.Frame(win, background="#bbbbbb")
        tbl.grid(row=r, column=0, columnspan=2, sticky="w", **pad)
        for c, nom in enumerate(noms_cols):
            tk.Label(tbl, text=nom, font=("", 9, "bold"), background="#e8e8e8",
                     foreground="#222", padx=7, pady=4, borderwidth=1, relief="solid").grid(
                row=0, column=c, sticky="nsew")
        for i, (m, ligne) in enumerate(zip(table, lignes_tableau(table)), start=1):
            for c, (nom, val) in enumerate(zip(noms_cols, ligne)):
                bg, fg, gras = "#ffffff", "#222", False
                if nom in col_metrique:
                    bg, fg = couleurs[m.niveaux[col_metrique[nom]].name]
                elif nom == "niveau":
                    bg, fg, gras = (*couleurs[m.niveau.name], True)
                tk.Label(tbl, text=val, font=("", 9, "bold" if gras else "normal"),
                         background=bg, foreground=fg, padx=7, pady=4,
                         borderwidth=1, relief="solid").grid(row=i, column=c, sticky="nsew")
        r += 1
        ttk.Label(
            win, text="RSS suivi de « ! » = distance réelle < distance de sécurité RSS.",
            foreground="#888",
        ).grid(row=r, column=0, columnspan=2, sticky="w", **pad)
        r += 1

        # 3) Grille des seuils de référence (pour interpréter chaque valeur)
        ttk.Label(win, text="Seuils de référence", font=("", 10, "bold")).grid(
            row=r, column=0, columnspan=2, sticky="w", **pad
        )
        r += 1
        ref = tk.Text(win, height=7, width=82, font=("Courier", 9), wrap="none",
                      background="#1f1f1f", foreground="#eaeaea", relief="flat",
                      borderwidth=0, highlightthickness=0, padx=8, pady=6)
        ref.insert("1.0", format_seuils())
        ref.configure(state="disabled")
        ref.grid(row=r, column=0, columnspan=2, sticky="ew", **pad)

    def _construire_contexte(self) -> ScenarioContext:
        return ScenarioContext(
            vitesse_ego_kmh=float(self.var_ego.get()),
            type_route=_depuis_valeur(TypeRoute, self.cb_type_route.get()),
            geometrie=_depuis_valeur(Geometrie, self.cb_geometrie.get()),
            limite_vitesse_kmh=float(self.cb_limite.get()),
            zone_travaux=bool(self.var_zone.get()),
            etat_route=_depuis_valeur(EtatRoute, self.cb_etat.get()),
            meteo=_depuis_valeur(Meteo, self.cb_meteo.get()),
            heure=_depuis_valeur(Heure, self.cb_heure.get()),
            visibilite_m=float(self.var_vis.get()),
            agents=list(self.agents),
        )

    def _lancer(self) -> None:
        ctx = self._construire_contexte()
        problemes = constraints.valider(ctx)
        if problemes:
            messagebox.showerror("Scénario incohérent", "\n".join("• " + p for p in problemes))
            return
        if not ctx.agents:
            if not messagebox.askyesno("Aucun agent", "Lancer sans aucun agent ?"):
                return
        self.result = ctx
        self.reaction = bool(self.var_reaction.get())
        self.master.destroy()


def demander_scenario() -> Optional[Tuple[ScenarioContext, bool]]:
    """Ouvre la fenêtre et renvoie (ScenarioContext, ego_freine) ou None si fermé."""
    root = tk.Tk()
    form = ScenarioForm(root)
    root.mainloop()
    if form.result is None:
        return None
    return form.result, form.reaction


if __name__ == "__main__":
    res = demander_scenario()
    print(res)
