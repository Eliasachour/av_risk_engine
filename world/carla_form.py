"""
Formulaire de configuration CARLA (tkinter).

Ouvre une fenêtre modale au lancement de `carla_run.py`. L'utilisateur configure
la connexion CARLA, la carte, le scénario (à partir d'un préréglage SC-XX ou de
zéro), et les options d'exécution. Le formulaire se ferme complètement avant
que Pygame ne prenne la main — les deux ne cohabitent pas dans le même process.

La configuration est **sauvegardée** dans `~/.av_risk_engine/carla_config.json`
et rechargée au démarrage suivant — plus besoin de tout retaper.
"""
from __future__ import annotations

import json
import tkinter as tk
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tkinter import ttk
from typing import List, Optional

from risk_engine import (
    Agent,
    EtatRoute,
    Geometrie,
    Heure,
    Meteo,
    ScenarioContext,
    TypeAgent,
    TypeRoute,
)

CONFIG_PATH = Path.home() / ".av_risk_engine" / "carla_config.json"

CARTES_STANDARD = ["Town01", "Town02", "Town03", "Town04", "Town05", "Town10HD"]


@dataclass
class CarlaConfig:
    """Toute la configuration d'une session CARLA."""
    # --- Connexion CARLA ---
    host: str = "localhost"
    port: int = 2000
    carte: str = "Town04"
    tick_hz: int = 20
    # --- Scénario ---
    preset_id: str = ""              # "" = pas de préréglage, on utilise les champs bruts
    vitesse_ego_kmh: float = 50.0
    type_route: str = "nationale"
    geometrie: str = "droite"
    limite_vitesse_kmh: int = 90
    zone_travaux: bool = False
    etat_route: str = "sec"
    meteo: str = "clair"
    heure: str = "jour"
    visibilite_m: float = 500.0
    agents_json: str = "[]"           # sérialisation des agents (édition brute)
    # --- Contrôle ---
    reaction: bool = True
    duree_max_s: float = 30.0
    log_csv: bool = True


def charger_config() -> CarlaConfig:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            return CarlaConfig(**{k: v for k, v in data.items() if k in CarlaConfig.__dataclass_fields__})
        except Exception:
            pass
    return CarlaConfig()


def sauvegarder_config(cfg: CarlaConfig) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(cfg), indent=2))


def config_vers_contexte(cfg: CarlaConfig) -> ScenarioContext:
    """Traduit la config du formulaire en `ScenarioContext` pour le moteur."""
    agents_data = json.loads(cfg.agents_json or "[]")
    agents = [
        Agent(
            type_agent=TypeAgent(a["type_agent"]),
            vitesse_kmh=a.get("vitesse_kmh", 0.0),
            distance_m=a.get("distance_m", 30.0),
            cap_relatif_deg=a.get("cap_relatif_deg", 0.0),
            acceleration_ms2=a.get("acceleration_ms2", 0.0),
            ecart_lateral_m=a.get("ecart_lateral_m", 0.0),
            profondeur_mesuree=a.get("profondeur_mesuree", True),
        )
        for a in agents_data
    ]
    return ScenarioContext(
        vitesse_ego_kmh=cfg.vitesse_ego_kmh,
        type_route=TypeRoute(cfg.type_route),
        geometrie=Geometrie(cfg.geometrie),
        limite_vitesse_kmh=cfg.limite_vitesse_kmh,
        zone_travaux=cfg.zone_travaux,
        etat_route=EtatRoute(cfg.etat_route),
        meteo=Meteo(cfg.meteo),
        heure=Heure(cfg.heure),
        visibilite_m=cfg.visibilite_m,
        agents=agents,
    )


class FormulaireCarla:
    """Formulaire tkinter — bloquant, retourne un `CarlaConfig` ou `None`."""

    def __init__(self):
        self.result: Optional[CarlaConfig] = None
        self.cfg = charger_config()
        self.root = tk.Tk()
        self.root.title("AV Risk Engine — Configuration CARLA")
        self.root.geometry("560x720")
        self._build()

    def _build(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Onglet 1 : Connexion CARLA ---
        f1 = ttk.Frame(notebook, padding=12)
        notebook.add(f1, text="CARLA")

        ttk.Label(f1, text="Serveur CARLA", font=("", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(f1, text="Hôte :").grid(row=1, column=0, sticky="w")
        self.host = tk.StringVar(value=self.cfg.host)
        ttk.Entry(f1, textvariable=self.host, width=30).grid(row=1, column=1, sticky="w")
        ttk.Label(f1, text="Port :").grid(row=2, column=0, sticky="w")
        self.port = tk.IntVar(value=self.cfg.port)
        ttk.Entry(f1, textvariable=self.port, width=10).grid(row=2, column=1, sticky="w")

        ttk.Separator(f1).grid(row=3, columnspan=2, sticky="ew", pady=10)

        ttk.Label(f1, text="Monde", font=("", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(0, 6))
        ttk.Label(f1, text="Carte :").grid(row=5, column=0, sticky="w")
        self.carte = tk.StringVar(value=self.cfg.carte)
        ttk.Combobox(f1, textvariable=self.carte, values=CARTES_STANDARD, width=20).grid(row=5, column=1, sticky="w")
        ttk.Label(f1, text="Tick rate (Hz) :").grid(row=6, column=0, sticky="w")
        self.tick_hz = tk.IntVar(value=self.cfg.tick_hz)
        ttk.Spinbox(f1, from_=10, to=30, textvariable=self.tick_hz, width=8).grid(row=6, column=1, sticky="w")

        # --- Onglet 2 : Scénario ---
        f2 = ttk.Frame(notebook, padding=12)
        notebook.add(f2, text="Scénario")

        # Préréglages
        ttk.Label(f2, text="Préréglage", font=("", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.preset = tk.StringVar(value=self.cfg.preset_id)
        try:
            from calibration.scenarios_ref import REFERENCES
            presets = [""] + [f"{r.id} — {r.nom}" for r in REFERENCES]
            self._preset_map = {f"{r.id} — {r.nom}": r for r in REFERENCES}
        except Exception:
            presets = [""]
            self._preset_map = {}
        cb = ttk.Combobox(f2, textvariable=self.preset, values=presets, width=42, state="readonly")
        cb.grid(row=1, column=0, columnspan=2, sticky="ew")
        cb.bind("<<ComboboxSelected>>", self._on_preset)

        ttk.Separator(f2).grid(row=2, columnspan=2, sticky="ew", pady=10)

        # Route + environnement
        ttk.Label(f2, text="Route et environnement", font=("", 10, "bold")).grid(row=3, column=0, sticky="w")
        self.type_route = self._enum_select(f2, "Type de route :", TypeRoute, self.cfg.type_route, 4)
        self.geometrie = self._enum_select(f2, "Géométrie :", Geometrie, self.cfg.geometrie, 5)
        self.limite = self._int_field(f2, "Limite (km/h) :", self.cfg.limite_vitesse_kmh, 6)
        self.travaux = tk.BooleanVar(value=self.cfg.zone_travaux)
        ttk.Checkbutton(f2, text="Zone de travaux", variable=self.travaux).grid(row=7, column=1, sticky="w")
        self.meteo = self._enum_select(f2, "Météo :", Meteo, self.cfg.meteo, 8)
        self.etat_route = self._enum_select(f2, "État route :", EtatRoute, self.cfg.etat_route, 9)
        self.heure = self._enum_select(f2, "Heure :", Heure, self.cfg.heure, 10)
        self.vis = self._float_field(f2, "Visibilité (m) :", self.cfg.visibilite_m, 11)

        ttk.Separator(f2).grid(row=12, columnspan=2, sticky="ew", pady=10)

        # Ego
        ttk.Label(f2, text="Véhicule ego", font=("", 10, "bold")).grid(row=13, column=0, sticky="w")
        self.vitesse_ego = self._float_field(f2, "Vitesse (km/h) :", self.cfg.vitesse_ego_kmh, 14)

        ttk.Separator(f2).grid(row=15, columnspan=2, sticky="ew", pady=10)

        # Agents (édition JSON brute, simple pour l'étape 1)
        ttk.Label(f2, text="Agents (JSON)", font=("", 10, "bold")).grid(row=16, column=0, sticky="w")
        self.agents_txt = tk.Text(f2, height=6, width=54, font=("Courier", 9))
        self.agents_txt.grid(row=17, columnspan=2, sticky="ew", pady=(4, 0))
        self.agents_txt.insert("1.0", self.cfg.agents_json or "[]")
        ttk.Label(f2, text='Ex : [{"type_agent":"pieton","vitesse_kmh":5,"distance_m":25,"cap_relatif_deg":90,"ecart_lateral_m":5}]',
                  font=("", 8), foreground="#888").grid(row=18, columnspan=2, sticky="w")

        # --- Onglet 3 : Contrôle ---
        f3 = ttk.Frame(notebook, padding=12)
        notebook.add(f3, text="Contrôle")
        self.reaction = tk.BooleanVar(value=self.cfg.reaction)
        ttk.Checkbutton(f3, text="L'ego réagit (freinage automatique)", variable=self.reaction).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(f3, text="Durée max (s) :").grid(row=1, column=0, sticky="w")
        self.duree = tk.DoubleVar(value=self.cfg.duree_max_s)
        ttk.Entry(f3, textvariable=self.duree, width=10).grid(row=1, column=1, sticky="w")
        self.log = tk.BooleanVar(value=self.cfg.log_csv)
        ttk.Checkbutton(f3, text="Enregistrer un log CSV", variable=self.log).grid(row=2, column=0, sticky="w", pady=4)

        # --- Boutons ---
        f_btn = ttk.Frame(self.root, padding=10)
        f_btn.pack(fill="x", side="bottom")
        ttk.Button(f_btn, text="Annuler", command=self._annuler).pack(side="right", padx=4)
        ttk.Button(f_btn, text="Lancer sur CARLA", command=self._lancer).pack(side="right")

    def _enum_select(self, parent, label, enum_cls, valeur, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        var = tk.StringVar(value=valeur)
        ttk.Combobox(parent, textvariable=var, values=[e.value for e in enum_cls],
                     state="readonly", width=20).grid(row=row, column=1, sticky="w")
        return var

    def _int_field(self, parent, label, valeur, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        var = tk.IntVar(value=valeur)
        ttk.Entry(parent, textvariable=var, width=10).grid(row=row, column=1, sticky="w")
        return var

    def _float_field(self, parent, label, valeur, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        var = tk.DoubleVar(value=valeur)
        ttk.Entry(parent, textvariable=var, width=10).grid(row=row, column=1, sticky="w")
        return var

    def _on_preset(self, _event):
        """Charge les valeurs d'un préréglage SC-XX dans les champs du formulaire."""
        choix = self.preset.get()
        if choix not in self._preset_map:
            return
        r = self._preset_map[choix]
        c = r.ctx
        self.type_route.set(c.type_route.value)
        self.geometrie.set(c.geometrie.value)
        self.limite.set(c.limite_vitesse_kmh)
        self.travaux.set(c.zone_travaux)
        self.meteo.set(c.meteo.value)
        self.etat_route.set(c.etat_route.value)
        self.heure.set(c.heure.value)
        self.vis.set(c.visibilite_m)
        self.vitesse_ego.set(c.vitesse_ego_kmh)
        agents_data = [
            {
                "type_agent": ag.type_agent.value,
                "vitesse_kmh": ag.vitesse_kmh,
                "distance_m": ag.distance_m,
                "cap_relatif_deg": ag.cap_relatif_deg,
                "ecart_lateral_m": ag.ecart_lateral_m,
                "acceleration_ms2": ag.acceleration_ms2,
                "profondeur_mesuree": ag.profondeur_mesuree,
            }
            for ag in c.agents
        ]
        self.agents_txt.delete("1.0", "end")
        self.agents_txt.insert("1.0", json.dumps(agents_data, indent=2))

    def _lancer(self):
        cfg = CarlaConfig(
            host=self.host.get(),
            port=self.port.get(),
            carte=self.carte.get(),
            tick_hz=self.tick_hz.get(),
            preset_id=(self.preset.get().split(" — ")[0] if self.preset.get() else ""),
            vitesse_ego_kmh=self.vitesse_ego.get(),
            type_route=self.type_route.get(),
            geometrie=self.geometrie.get(),
            limite_vitesse_kmh=self.limite.get(),
            zone_travaux=self.travaux.get(),
            etat_route=self.etat_route.get(),
            meteo=self.meteo.get(),
            heure=self.heure.get(),
            visibilite_m=self.vis.get(),
            agents_json=self.agents_txt.get("1.0", "end").strip() or "[]",
            reaction=self.reaction.get(),
            duree_max_s=self.duree.get(),
            log_csv=self.log.get(),
        )
        sauvegarder_config(cfg)
        self.result = cfg
        self.root.destroy()

    def _annuler(self):
        self.root.destroy()

    def executer(self) -> Optional[CarlaConfig]:
        self.root.mainloop()
        return self.result
