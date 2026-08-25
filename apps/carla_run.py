"""
Point d'entrée CARLA — Étape 2 : perception + contrôle automatique + HUD enrichi.

Enchaîne :
  1. Formulaire tkinter → CarlaConfig.
  2. Fermeture tkinter, ouverture Pygame HUD enrichi.
  3. Boucle synchrone : tick CARLA → contexte → assess_risk
     → commande_recommandee → VehicleControl + HUD + log CSV.

L'ego pilote seul :
  - freinage physique fondé sur commande_recommandee (risk_engine/control.py) ;
  - reprise ACC vers la vitesse cible quand SAFE (world/carla_control.py) ;
  - pilotage latéral simple par suivi de voie (world/carla_control.py).

Usage :
    python3 apps/carla_run.py

Prérequis :
  - CARLA 0.9.15 en cours d'exécution (./CarlaUE4.sh sous Linux).
  - Python 3.8+ avec les paquets : carla (wheel CARLA), pygame, numpy.
"""
from __future__ import annotations


# Ajoute la racine du depot au sys.path pour permettre les imports metier
# (risk_engine, sim, scenarios, calibration, world) meme quand ce script est
# lance directement (`python3 apps/foo.py`). Voir apps/__init__.py.
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))


import csv
import math
import sys
import time
from pathlib import Path
from typing import List, Optional


def main() -> int:
    # 1. Formulaire ------------------------------------------------------
    print("→ Ouverture du formulaire de configuration...")
    from world.carla_form import FormulaireCarla, config_vers_contexte

    cfg = FormulaireCarla().executer()
    if cfg is None:
        print("Configuration annulée.")
        return 0

    print(f"→ Configuration : CARLA {cfg.host}:{cfg.port}, carte {cfg.carte}, tick {cfg.tick_hz} Hz")
    print(f"→ Scénario : ego {cfg.vitesse_ego_kmh:.0f} km/h, {cfg.meteo}/{cfg.etat_route}")

    # 2. Contexte moteur --------------------------------------------------
    try:
        ctx = config_vers_contexte(cfg)
    except Exception as e:
        print(f"✗ Configuration invalide : {e}")
        return 1
    print(f"→ {len(ctx.agents)} agent(s) à spawner")

    # 3. Vérifications préalables (imports optionnels) --------------------
    try:
        from world.carla_bridge import CarlaBridge
    except RuntimeError as e:
        print(f"✗ CARLA introuvable : {e}")
        return 2
    try:
        from world.hud import HUD, HUDState
    except RuntimeError as e:
        print(f"✗ Pygame introuvable : {e}")
        return 3

    from risk_engine import assess_risk, RiskLevel

    # 4. Log CSV ---------------------------------------------------------
    log_writer = None
    log_file = None
    if cfg.log_csv:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"carla_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        log_file = open(log_path, "w", newline="", encoding="utf-8")
        log_writer = csv.writer(log_file)
        log_writer.writerow([
            "t", "niveau_global", "vitesse_ego_kmh",
            "n_agents", "ttc_min", "drac_max", "distance_min",
            "collision",
        ])
        print(f"→ Log CSV : {log_path}")

    # 5. Session CARLA + HUD ---------------------------------------------
    dt = 1.0 / cfg.tick_hz
    camera_actor = None
    camera_image: Optional["np.ndarray"] = None  # dernière image caméra reçue

    def _on_camera(image):
        """Callback caméra : convertit BGRA → RGB numpy pour Pygame."""
        import numpy as np
        arr = np.frombuffer(image.raw_data, dtype=np.uint8)
        arr = arr.reshape((image.height, image.width, 4))[:, :, :3]  # BGRA → BGR
        arr = arr[:, :, ::-1]  # BGR → RGB
        nonlocal camera_image
        camera_image = arr.copy()

    hud = HUD(largeur=1280, hauteur=720)
    hud.demarrer()
    print("→ HUD ouvert. ESC pour quitter, ESPACE pour pause.")

    try:
        with CarlaBridge(host=cfg.host, port=cfg.port,
                         fixed_delta_seconds=dt) as pont:
            print(f"→ Chargement de la carte {cfg.carte}...")
            pont.charger_carte(cfg.carte)

            print("→ Application du scénario (spawn ego + agents)...")
            pont.appliquer_scenario(ctx)

            # Caméra RGB attachée à l'ego, orientée vers l'avant.
            import carla  # noqa: F401 (importé pour la caméra)
            bp_lib = pont.world.get_blueprint_library()
            bp_cam = bp_lib.find("sensor.camera.rgb")
            bp_cam.set_attribute("image_size_x", "960")
            bp_cam.set_attribute("image_size_y", "540")
            bp_cam.set_attribute("fov", "90")
            cam_tf = carla.Transform(carla.Location(x=-4.5, z=2.5),
                                     carla.Rotation(pitch=-10.0))
            camera_actor = pont.world.spawn_actor(bp_cam, cam_tf, attach_to=pont.ego)
            camera_actor.listen(_on_camera)

            t_debut = time.time()
            t_sim = 0.0

            # Imports pour le contrôle
            from risk_engine import commande_recommandee, ObsAgent
            from world.carla_bridge import _vitesse_ms

            # ---------------- Boucle principale --------------------
            while hud.actif():
                hud.gerer_evenements()
                if hud.en_pause():
                    # En pause : geler l'ego avec un frein léger
                    if cfg.reaction:
                        pont.ego.apply_control(carla.VehicleControl(brake=1.0))
                    hud.attacher_image_camera(camera_image)
                    hud.rendre(HUDState(
                        t=t_sim, niveau=RiskLevel.SAFE,
                        vitesse_ego_kmh=_vitesse_ms(pont.ego) * 3.6,
                        freinage=True, agent_critique=None,
                        n_agents=len(pont.agents), diagnostic="Pause",
                        mu_g=None, mode_ctrl="pause",
                        agents_detail=[], v_cible_kmh=cfg.vitesse_ego_kmh,
                    ))
                    continue

                # Tick CARLA + évaluation
                pont.tick()
                t_sim += dt
                ctx_t = pont.contexte_courant()
                verdict = assess_risk(ctx_t)

                # ------- Étape 2 : commande de contrôle -------
                v_ego_ms = _vitesse_ms(pont.ego)
                cmd = None
                if cfg.reaction:
                    from world.carla_control import pilotage_lateral, reprise_acc

                    # Position monde de l'ego + observations des agents (repère monde)
                    ego_tf = pont.ego.get_transform()
                    ego_x, ego_y = ego_tf.location.x, ego_tf.location.y
                    obs = []
                    for actor, detail in zip(pont.agents, verdict.details):
                        loc = actor.get_transform().location
                        obs.append(ObsAgent(x=loc.x, y=loc.y, drac=detail.drac))
                    cmd = commande_recommandee(verdict, ctx_t, ego_x, ego_y, obs)

                    # Reprise ACC : si SAFE, viser la vitesse cible (respecte la limite)
                    v_cible_ms = min(cfg.vitesse_ego_kmh, ctx_t.limite_vitesse_kmh) / 3.6
                    throttle_acc = reprise_acc(cmd.mode, v_ego_ms, v_cible_ms)
                    if throttle_acc > 0:
                        throttle, brake = throttle_acc, 0.0
                    else:
                        throttle, brake = cmd.throttle, cmd.brake

                    # Pilotage latéral : suivi de voie via waypoint
                    steer = pilotage_lateral(pont, ego_tf, v_ego_ms)

                    pont.ego.apply_control(carla.VehicleControl(
                        throttle=throttle, brake=brake, steer=steer,
                    ))

                # Agent le plus critique (le pire niveau)
                ag_critique = None
                agents_detail = []
                if verdict.details:
                    for detail, actor in zip(verdict.details, pont.agents):
                        loc = actor.get_transform().location
                        ego_loc = pont.ego.get_transform().location
                        d = math.hypot(loc.x - ego_loc.x, loc.y - ego_loc.y)
                        agents_detail.append({
                            "type": detail.agent.type_agent.value,
                            "distance": d,
                            "ttc": detail.ttc if math.isfinite(detail.ttc) else None,
                            "thw": detail.thw if math.isfinite(detail.thw) else None,
                            "drac": detail.drac,
                            "rss": detail.rss_min,
                            "niveau": detail.level,
                        })
                    # Le plus critique = plus haut niveau puis plus petit TTC
                    ag_critique = max(agents_detail,
                                       key=lambda a: (
                                           ["SAFE", "WATCH", "DANGER", "CRITICAL"].index(a["niveau"].name),
                                           -(a["ttc"] if a["ttc"] is not None else 1e9),
                                       ))

                # Rendu HUD
                hud.attacher_image_camera(camera_image)
                hud.rendre(HUDState(
                    t=t_sim,
                    niveau=verdict.level,
                    vitesse_ego_kmh=v_ego_ms * 3.6,
                    freinage=(cmd.brake > 0.05 if cmd else False),
                    agent_critique=ag_critique,
                    n_agents=len(pont.agents),
                    diagnostic=(f"{cmd.mode.capitalize()} · µ·g = {cmd.mu_g:.1f} m/s²"
                                if cmd else f"Perception seule · {cfg.tick_hz} Hz"),
                    mu_g=cmd.mu_g if cmd else None,
                    mode_ctrl=cmd.mode if cmd else "off",
                    agents_detail=agents_detail,
                    v_cible_kmh=cfg.vitesse_ego_kmh,
                ))

                # Log CSV
                if log_writer:
                    ttcs = [d.ttc for d in verdict.details if math.isfinite(d.ttc)]
                    log_writer.writerow([
                        f"{t_sim:.2f}",
                        verdict.level.name,
                        f"{v_ego_ms * 3.6:.1f}",
                        len(verdict.details),
                        f"{min(ttcs):.2f}" if ttcs else "",
                        f"{max((d.drac for d in verdict.details), default=0.0):.2f}",
                        f"{min((ctx_t.agents[i].distance_m for i in range(len(ctx_t.agents))), default=0.0):.1f}",
                        "1" if hasattr(pont.ego, "is_alive") and not pont.ego.is_alive else "0",
                    ])

                # Fin par durée
                if t_sim >= cfg.duree_max_s:
                    print(f"→ Durée max atteinte ({cfg.duree_max_s}s)")
                    break

            duree = time.time() - t_debut
            print(f"→ Simulation terminée : {t_sim:.1f}s simulés en {duree:.1f}s réels")

    except KeyboardInterrupt:
        print("\n→ Interruption utilisateur")
    except Exception as e:
        print(f"✗ Erreur : {e}")
        import traceback
        traceback.print_exc()
        return 4
    finally:
        if camera_actor is not None and camera_actor.is_alive:
            camera_actor.destroy()
        hud.fermer()
        if log_file is not None:
            log_file.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
