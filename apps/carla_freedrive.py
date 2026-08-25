#!/usr/bin/env python3
"""
Point d'entrée CARLA — Mode conduite libre.

Tout se passe dans une seule fenêtre : le menu de configuration, puis le HUD.
Plus de formulaire tkinter séparé.

Le conducteur pilote l'ego au clavier, le monde CARLA vit tout seul (véhicules
IA gérés par le Traffic Manager, piétons IA gérés par Walker AI Controllers),
et le moteur d'analyse observe ce qui se passe.

La météo se change EN DIRECT depuis le HUD (F1 à F7 pour les préréglages,
I/K O/L P/M N/B pour les réglages fins). Le contexte transmis au moteur suit
automatiquement : changer pour « neige / verglas » fait chuter mu.g et le
moteur devient plus sévère dans la seconde.

Trois niveaux d'assistance, choisis dans le menu :
    eval    le moteur affiche, aucune intervention
    alerte  + alerte visuelle pulsante en DANGER / CRITICAL
    aeb     + freinage automatique si CRITICAL persistant

Commandes : voir la touche H dans le HUD.

Usage :
    python apps/carla_freedrive.py

Prérequis : CARLA (0.9.15 ou 0.9.16) démarré, paquets carla + pygame + numpy.
"""
from __future__ import annotations

# Ajoute la racine du depot au sys.path
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import csv
import math
import sys
import time
from dataclasses import replace
from pathlib import Path


CARTES = ["Town01", "Town02", "Town03", "Town04", "Town05", "Town10HD"]


def _construire_menu(screen):
    """Construit le menu de configuration et renvoie (MenuConfig, reglages)."""
    from world.hud import MenuConfig, Reglage

    reglages = [
        Reglage("carte", "Carte", CARTES, index=3,
                aide="Town04 : autoroute et grandes courbes. Town02 : petite ville dense."),
        Reglage("tick_hz", "Tick rate", [10, 15, 20, 25, 30], index=2,
                aide="Frequence de simulation. Baisser a 15 Hz si CARLA broute.",
                format=lambda v: f"{v} Hz"),
        Reglage("n_vehicules_ia", "Vehicules IA", [0, 5, 10, 20, 30, 50, 80], index=2,
                aide="Trafic autonome gere par le Traffic Manager de CARLA."),
        Reglage("n_pietons_ia", "Pietons IA", [0, 5, 10, 20, 30, 50], index=1,
                aide="Pietons autonomes. Sur petite carte, rester modeste."),
        Reglage("assistance", "Assistance moteur", ["eval", "alerte", "aeb"], index=1,
                aide="eval : observe seulement. alerte : signale. aeb : freine a votre place.",
                format=lambda v: {"eval": "evaluation seule",
                                  "alerte": "alerte visuelle",
                                  "aeb": "freinage d'urgence (AEB)"}[v]),
        Reglage("meteo_depart", "Meteo de depart",
                ["Clair", "Couvert", "Pluie", "Orage", "Brouillard",
                 "Neige / verglas", "Nuit claire"], index=0,
                aide="Modifiable a tout moment en cours de route avec F1 a F7."),
        Reglage("vitesse_cible_kmh", "Vitesse de reference",
                [30, 50, 70, 90, 110, 130], index=1,
                aide="Sert de repere sur la jauge de vitesse du HUD.",
                format=lambda v: f"{v} km/h"),
        Reglage("rayon_perception_m", "Rayon de perception",
                [30, 45, 60, 80, 100], index=2,
                aide="Distance au-dela de laquelle le moteur ignore un acteur.",
                format=lambda v: f"{v} m"),
        Reglage("demi_angle_perception_deg", "Demi-angle du cone",
                [30, 45, 60, 90, 180], index=2,
                aide="180 deg = perception omnidirectionnelle.",
                format=lambda v: f"+/- {v} deg"),
        Reglage("duree_max_s", "Duree max", [60, 120, 300, 600, 1800], index=2,
                aide="Arret automatique passe ce delai.",
                format=lambda v: f"{v//60} min" if v >= 60 else f"{v} s"),
        Reglage("log_csv", "Log CSV", [True, False], index=0,
                aide="Ecrit un fichier logs/freedrive_*.csv, une ligne par tick."),
    ]
    menu = MenuConfig(
        screen, reglages,
        titre="AV Risk Engine - Conduite libre",
        sous_titre="Vous conduisez, le moteur evalue le risque en temps reel.",
    )
    return menu, reglages


def main() -> int:
    # --- 1. Ouvrir la fenêtre et afficher le menu ---------------------
    try:
        import pygame
        from world.hud import HUD, HUDState, MenuConfig, ControleMeteo
    except (ImportError, RuntimeError) as e:
        print(f"X Pygame introuvable : {e}")
        return 3

    pygame.init()
    pygame.display.set_caption("AV Risk Engine - CARLA")
    LARGEUR, HAUTEUR = 1280, 720
    screen = pygame.display.set_mode((LARGEUR, HAUTEUR))

    menu, _ = _construire_menu(screen)
    if not menu.boucle():
        print("Configuration annulee.")
        pygame.quit()
        return 0
    cfg = menu.valeurs()

    print(f"-> Carte {cfg['carte']}, {cfg['tick_hz']} Hz")
    print(f"-> Trafic : {cfg['n_vehicules_ia']} vehicules, {cfg['n_pietons_ia']} pietons")
    print(f"-> Assistance : {cfg['assistance']}")
    print(f"-> Meteo de depart : {cfg['meteo_depart']}")

    # Écran d'attente pendant que CARLA charge (le chargement peut durer 10-30 s)
    screen.fill((26, 31, 46))
    f = pygame.font.SysFont("Arial", 22, bold=True)
    screen.blit(f.render(f"Chargement de {cfg['carte']} dans CARLA...", True,
                         (255, 255, 255)), (60, HAUTEUR // 2 - 20))
    f2 = pygame.font.SysFont("Arial", 14)
    screen.blit(f2.render("Cela peut prendre une trentaine de secondes.", True,
                          (154, 163, 179)), (60, HAUTEUR // 2 + 14))
    pygame.display.flip()

    # --- 2. Contexte moteur de base -----------------------------------
    from risk_engine import (
        Agent, Geometrie, ScenarioContext, TypeRoute, assess_risk, RiskLevel,
    )
    from risk_engine.context import EtatRoute, Heure, Meteo

    ctx_base = ScenarioContext(
        vitesse_ego_kmh=float(cfg["vitesse_cible_kmh"]),
        type_route=TypeRoute.URBAIN,
        geometrie=Geometrie.DROITE,
        limite_vitesse_kmh=int(cfg["vitesse_cible_kmh"]),
        zone_travaux=False,
        etat_route=EtatRoute.SEC,
        meteo=Meteo.CLAIR,
        heure=Heure.JOUR,
        visibilite_m=800.0,
        agents=[],
    )

    try:
        from world.carla_bridge import CarlaBridge, _vitesse_ms
    except RuntimeError as e:
        print(f"X CARLA introuvable : {e}")
        pygame.quit()
        return 2

    from risk_engine import metrics as metrics_mod, modifiers, recommander
    from world.aeb import Assistance
    from world.keyboard_control import ControleClavier
    from world.env_sensors import (
        DetecteurCollision, DetecteurObstacle, contexte_route,
    )
    from world.perception_oracle import acteurs_percus, contexte_depuis_perception
    from world.traffic import GestionnaireTrafic

    # --- 3. Log CSV ----------------------------------------------------
    log_writer = log_file = None
    if cfg["log_csv"]:
        log_dir = _ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"freedrive_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        log_file = open(log_path, "w", newline="", encoding="utf-8")
        log_writer = csv.writer(log_file)
        log_writer.writerow([
            "t", "niveau", "vitesse_ego_kmh", "n_percus", "ttc_min", "drac_max",
            "distance_min", "meteo", "etat_route", "visibilite_m",
            "assistance", "aeb_engage", "conducteur_freine",
        ])
        print(f"-> Log CSV : {log_path}")

    dt = 1.0 / cfg["tick_hz"]
    camera_image = None
    camera_actor = None
    det_obstacle = det_collision = None

    def _on_camera(image):
        import numpy as np
        arr = np.frombuffer(image.raw_data, dtype=np.uint8)
        arr = arr.reshape((image.height, image.width, 4))[:, :, :3][:, :, ::-1]
        nonlocal camera_image
        camera_image = arr.copy()

    hud = HUD(largeur=LARGEUR, hauteur=HAUTEUR)
    hud.attacher(screen)          # réutilise la fenêtre ouverte par le menu

    controle = ControleClavier()
    assistance = Assistance(mode=cfg["assistance"])

    try:
        with CarlaBridge(host="localhost", port=2000,
                         fixed_delta_seconds=dt) as pont:
            print(f"-> Chargement de la carte {cfg['carte']}...")
            pont.charger_carte(cfg["carte"])

            import carla
            import random
            random.seed(42)

            print("-> Spawn de l'ego...")
            spawn_points = pont.world.get_map().get_spawn_points()
            if not spawn_points:
                raise RuntimeError("Aucun point de spawn sur cette carte.")
            spawn = random.choice(spawn_points)
            bpl = pont.world.get_blueprint_library()
            ego_c = bpl.filter("vehicle.tesla.model3") or bpl.filter("vehicle.*")
            if not ego_c:
                raise RuntimeError("Aucun blueprint de vehicule disponible.")
            bp_ego = ego_c[0]
            bp_ego.set_attribute("role_name", "ego")
            pont.ego = pont.world.spawn_actor(bp_ego, spawn)
            pont._ctx_base = ctx_base
            # Un tick est INDISPENSABLE ici : en mode synchrone, get_transform()
            # lit le dernier instantané du monde. Sans ce tick, l'ego est vu en
            # (0,0,0) et le filtrage par distance du trafic ne trouve aucun
            # point de spawn — d'où les « 0 véhicules » observés.
            pont.world.tick()

            # Météo : contrôleur temps réel, aligné sur le choix du menu
            meteo = ControleMeteo(pont.world, ctx_base)
            from world.hud.weather_control import PRESETS
            for i, p in enumerate(PRESETS):
                if p.nom == cfg["meteo_depart"]:
                    meteo._charger_preset(i)
                    break
            meteo.appliquer_si_besoin()

            # Caméra
            bp_cam = bpl.find("sensor.camera.rgb")
            bp_cam.set_attribute("image_size_x", "960")
            bp_cam.set_attribute("image_size_y", "540")
            bp_cam.set_attribute("fov", "90")
            cam_tf = carla.Transform(carla.Location(x=-4.5, z=2.5),
                                     carla.Rotation(pitch=-10.0))
            camera_actor = pont.world.spawn_actor(bp_cam, cam_tf, attach_to=pont.ego)
            camera_actor.listen(_on_camera)

            # Capteurs d'environnement : c'est eux qui font voir les murs au
            # moteur, et qui enregistrent les collisions reelles.
            det_obstacle = DetecteurObstacle(
                pont.world, pont.ego,
                portee_m=float(cfg["rayon_perception_m"]), rayon_m=1.2)
            det_collision = DetecteurCollision(pont.world, pont.ego)

            # Adherence simulee alignee sur l'etat de route vu par le moteur.
            ratio = meteo.appliquer_friction(pont.ego)
            if ratio is not None:
                print(f"-> Friction pneus alignee sur l'etat de route (ratio {ratio:.2f})")

            print("-> Spawn du trafic IA...")
            with GestionnaireTrafic(
                pont.world, pont.tm,
                n_vehicules=cfg["n_vehicules_ia"],
                n_pietons=cfg["n_pietons_ia"],
            ) as trafic:
                trafic.spawn_autour_de(pont.ego, rayon_m=120.0,
                                       centre=spawn.location)

                print("-> C'est parti. H pour l'aide, F1-F7 pour la meteo.")
                # Cadence de la boucle = tick rate simule, sinon le temps
                # simule defile plus vite que le temps reel (conduite injouable).
                hud.cadence_hz = cfg["tick_hz"]
                t_debut = time.time()
                t_sim = 0.0

                while hud.actif():
                    hud.gerer_evenements()
                    # Les evenements non consommes par le HUD vont a la meteo
                    for ev in hud.evenements():
                        meteo.gerer_touche(ev)
                    meteo.appliquer_si_besoin()

                    keys = pygame.key.get_pressed()
                    ctx_courant = meteo.contexte()

                    if hud.en_pause():
                        pont.ego.apply_control(carla.VehicleControl(brake=1.0))
                        hud.attacher_image_camera(camera_image)
                        hud.rendre(HUDState(
                            t=t_sim, niveau=RiskLevel.SAFE,
                            vitesse_ego_kmh=_vitesse_ms(pont.ego) * 3.6,
                            freinage=True, agent_critique=None, n_agents=0,
                            diagnostic="Pause", mode_ctrl="pause",
                            mode_conduite="libre",
                            assistance=assistance.statut_court(),
                            meteo_resume=meteo.resume(),
                            v_cible_kmh=cfg["vitesse_cible_kmh"],
                            rayon_perception_m=cfg["rayon_perception_m"],
                            demi_angle_perception_deg=cfg["demi_angle_perception_deg"],
                        ))
                        continue

                    # --- Tick + perception + moteur ---
                    pont.tick()
                    t_sim += dt
                    det_obstacle.maj_temps(t_sim)
                    det_collision.maj_temps(t_sim)

                    # Contexte routier LU DANS LA CARTE : limite de vitesse du
                    # troncon, virage, feu tricolore. Ces champs etaient figes
                    # par le formulaire, donc faux des que l'ego changeait de rue.
                    cr = contexte_route(pont.world, pont.ego)
                    ctx_courant = replace(
                        ctx_courant,
                        limite_vitesse_kmh=cr.limite_vitesse_kmh,
                        geometrie=cr.geometrie,
                    )

                    # Regle admise : on ne peut pas percevoir plus loin qu'on ne
                    # voit. La portee effective est donc bornee par la visibilite
                    # meteo, ce qui rend le couple meteo/perception coherent.
                    portee = min(float(cfg["rayon_perception_m"]),
                                 ctx_courant.visibilite_m)
                    percus = acteurs_percus(
                        pont.world, pont.ego,
                        rayon_m=portee,
                        demi_angle_deg=cfg["demi_angle_perception_deg"],
                    )
                    ctx_t = contexte_depuis_perception(ctx_courant, pont.ego, percus)

                    # Obstacle STATIQUE devant (mur, glissiere, facade) : absent
                    # de la liste des acteurs, il laissait le moteur en SAFE
                    # meme en foncant dedans. On l'injecte comme agent immobile.
                    ag_mur = det_obstacle.agent_equivalent()
                    if ag_mur is not None:
                        ctx_t = replace(ctx_t, agents=list(ctx_t.agents) + [ag_mur])

                    verdict = assess_risk(ctx_t)

                    # --- Contrôle conducteur ---
                    v_ego_ms = _vitesse_ms(pont.ego)
                    ctrl_cond = controle.mise_a_jour(keys, dt)
                    cond_freine = controle.freinage_manuel_actif()
                    cond_accelere = ctrl_cond.throttle > 0.1

                    # --- Assistance ---
                    decision = assistance.decider(
                        verdict.level, t_sim,
                        conducteur_freine=cond_freine,
                        conducteur_accelere=cond_accelere,
                    )
                    if decision.override_brake:
                        ctrl_final = carla.VehicleControl(
                            throttle=0.0,
                            brake=max(ctrl_cond.brake, decision.override_brake_valeur),
                            steer=ctrl_cond.steer,
                        )
                    else:
                        ctrl_final = ctrl_cond
                    pont.ego.apply_control(ctrl_final)

                    # --- HUD ---
                    ego_tf = pont.ego.get_transform()
                    ego_loc = ego_tf.location
                    ego_yaw = math.radians(ego_tf.rotation.yaw)

                    # ATTENTION : verdict.details contient un element de plus que
                    # `percus` quand un mur a ete injecte. On apparie donc les N
                    # premiers (ordre preserve) puis on traite le mur a part.
                    agents_detail = []
                    for (actor, type_agent, st), detail in zip(percus, verdict.details):
                        dx = st.x - ego_loc.x
                        dy = st.y - ego_loc.y
                        agents_detail.append({
                            "type": type_agent.value,
                            "distance": math.hypot(dx, dy),
                            "ttc": detail.ttc if math.isfinite(detail.ttc) else None,
                            "thw": detail.thw if math.isfinite(detail.thw) else None,
                            "drac": detail.drac,
                            "rss": detail.rss_min,
                            "niveau": detail.level,
                            "dx_relatif": dx * math.cos(-ego_yaw) - dy * math.sin(-ego_yaw),
                            "dy_relatif": dx * math.sin(-ego_yaw) + dy * math.cos(-ego_yaw),
                        })
                    if ag_mur is not None and len(verdict.details) > len(percus):
                        d_mur = verdict.details[-1]
                        agents_detail.append({
                            "type": "obstacle fixe",
                            "distance": ag_mur.distance_m,
                            "ttc": d_mur.ttc if math.isfinite(d_mur.ttc) else None,
                            "thw": d_mur.thw if math.isfinite(d_mur.thw) else None,
                            "drac": d_mur.drac,
                            "rss": d_mur.rss_min,
                            "niveau": d_mur.level,
                            "dx_relatif": ag_mur.distance_m,
                            "dy_relatif": 0.0,
                        })

                    ordre = ["SAFE", "WATCH", "DANGER", "CRITICAL"]
                    ac = max(agents_detail,
                             key=lambda a: (ordre.index(a["niveau"].name),
                                            -(a["ttc"] if a["ttc"] is not None else 1e9)),
                             default=None)

                    # Les six metriques du pire agent, avec le niveau de chacune,
                    # pour affichage chiffre dans le HUD.
                    metriques = {}
                    decisive = ""
                    ttc_eff = marge = ratio_rss = corrob = None
                    if verdict.details:
                        pire = max(verdict.details,
                                   key=lambda d: (ordre.index(d.level.name),
                                                  -(d.ttc if math.isfinite(d.ttc) else 1e9)))
                        niv = pire.niveaux if isinstance(getattr(pire, "niveaux", None), dict) else {}
                        def _n(cle):
                            return niv.get(cle, pire.level)
                        metriques = {
                            "TTC":  (pire.ttc if math.isfinite(pire.ttc) else None, "s", _n("ttc")),
                            "THW":  (pire.thw if math.isfinite(pire.thw) else None, "s", _n("thw")),
                            "PET":  (pire.pet if math.isfinite(pire.pet) else None, "s", _n("pet")),
                            "RSS":  (pire.rss_min, "m", _n("rss")),
                            "CI":   (pire.ci, "", _n("ci")),
                            "DRAC": (pire.drac, "m/s2", _n("drac")),
                        }
                        decisive = str(getattr(pire, "metrique_decisive", "") or "").upper()
                        ttc_eff = (pire.ttc_effectif
                                   if math.isfinite(getattr(pire, "ttc_effectif", float("inf")))
                                   else None)
                        marge = getattr(pire, "marge", None)
                        ratio_rss = (pire.ratio_rss
                                     if math.isfinite(getattr(pire, "ratio_rss", float("inf")))
                                     else None)
                        corrob = getattr(pire, "corroboration", None)

                    # Consigne d'action : que faire pour revenir en SAFE.
                    reco = recommander(ctx_t, verdict)

                    facteur = t_sim / max(time.time() - t_debut, 1e-6)

                    hud.attacher_image_camera(camera_image)
                    hud.rendre(HUDState(
                        t=t_sim, niveau=verdict.level,
                        vitesse_ego_kmh=v_ego_ms * 3.6,
                        freinage=(ctrl_final.brake > 0.05),
                        agent_critique=ac, n_agents=len(agents_detail),
                        diagnostic=f"assistance {cfg['assistance']}",
                        mode_ctrl="manuel",
                        agents_detail=agents_detail,
                        v_cible_kmh=cfg["vitesse_cible_kmh"],
                        mode_conduite="libre",
                        assistance=assistance.statut_court(),
                        aeb_engage=decision.override_brake,
                        alerte_msg=decision.message,
                        meteo_resume=meteo.resume(),
                        mu_g=modifiers.mu(ctx_t.etat_route) * metrics_mod.G,
                        reco_message=reco.message,
                        reco_justification=reco.justification,
                        reco_urgence=reco.urgence,
                        rayon_perception_m=portee,
                        demi_angle_perception_deg=cfg["demi_angle_perception_deg"],
                        facteur_temps_reel=facteur,
                        fps=hud.clock.get_fps() if hud.clock else 0.0,
                        limite_vitesse_kmh=cr.limite_vitesse_kmh,
                        geometrie=cr.geometrie.value,
                        feu=cr.feu,
                        hors_voie=cr.hors_voie,
                        obstacle_statique_m=(ag_mur.distance_m if ag_mur else None),
                        n_collisions=det_collision.nombre,
                        collision_recente=det_collision.collision_recente(),
                        metriques=metriques,
                        metrique_decisive=decisive,
                        ratio_rss=ratio_rss,
                        ttc_effectif=ttc_eff,
                        marge_contextuelle=marge,
                        corroboration=corrob,
                    ))

                    if log_writer:
                        ttcs = [d.ttc for d in verdict.details if math.isfinite(d.ttc)]
                        log_writer.writerow([
                            f"{t_sim:.2f}", verdict.level.name,
                            f"{v_ego_ms * 3.6:.1f}", len(percus),
                            f"{min(ttcs):.2f}" if ttcs else "",
                            f"{max((d.drac for d in verdict.details), default=0.0):.2f}",
                            f"{min((a['distance'] for a in agents_detail), default=0.0):.1f}",
                            ctx_t.meteo.value, ctx_t.etat_route.value,
                            f"{ctx_t.visibilite_m:.0f}",
                            cfg["assistance"],
                            "oui" if decision.override_brake else "non",
                            "oui" if cond_freine else "non",
                        ])

                    if t_sim >= cfg["duree_max_s"]:
                        print(f"-> Duree max atteinte ({cfg['duree_max_s']} s)")
                        break

                print(f"-> Session terminee : {t_sim:.1f} s simules "
                      f"en {time.time() - t_debut:.1f} s reels")

    except KeyboardInterrupt:
        print("\n-> Interruption utilisateur")
    except Exception as e:
        print(f"X Erreur : {e}")
        import traceback
        traceback.print_exc()
        return 4
    finally:
        if camera_actor is not None and camera_actor.is_alive:
            camera_actor.destroy()
        pygame.quit()
        if log_file is not None:
            log_file.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
