#!/usr/bin/env python3
"""
Trajet A -> B : banc d'essai CARLA (Town03) - V8
- Bypass du mode PHYSIQUE en statut SAFE pour éviter les blocages intempestifs dans les virages.
- T-Bone et Couloir de sécurité actifs.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import argparse
import csv
import math
import os
import sys
import time
from dataclasses import replace

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
RAYON_PERCEPTION_M = 60.0            
DEMI_ANGLE_PERCEPTION_DEG = 120.0    

DELAI_GRACE_SPAWN_S = 2.0            
SEUIL_LATERAL_PIETON_M = 3.0        
SEUIL_LATERAL_VEHICULE_M = 2.5      
TOLERANCE_SUR_ITINERAIRE_M = 2.0    
HORIZON_ITINERAIRE_PTS = 15         
SEUIL_ALIGNEMENT_VOIE_DEG = 45.0    
TTC_IGNORE_S = 5.0                  
DIST_IGNORE_LOIN_M = 15.0          
DIST_IGNORE_ARRET_M = 12.0         

D_LOOK_MIN_M = 5.0                  
D_LOOK_MAX_M = 18.0                 
D_LOOK_GAIN = 1.5                   
SEUIL_V_LENTE_MS = 5.0             
GAIN_STEER_LENT = 1.5              
GAIN_STEER_RAPIDE = 0.8           
FACTEUR_COURBE_MIN = 0.4          

V_JAUNE_MS = 15.0 / 3.6           
DIST_SUIVI_M = 12.0             
DIST_ARRET_M = 4.5             
SEUIL_ARRET_MS = 0.5           
V_CIBLE_NULLE_MS = 0.1        
DEADBAND_V_MS = 0.3          
THROTTLE_MAX = 0.7          
BRAKE_MAX = 0.8            

FEU_ROUGE_S = 2.0    
FEU_VERT_S = 12.0
FEU_JAUNE_S = 2.0

DIST_REPRISE_M = 6.5          

DIST_PROXIMITE_CRITIQUE_M = 3.5   
DIST_CONTACT_M = 2.5              
DEMI_LARGEUR_COULOIR_M = 1.5      
SEUIL_APPROCHE_MS = 2.0          
RAYON_CONVERGENCE_M = 40.0       

RAYON_FEU_DEVANT_M = 40.0        

SEUIL_IMMOBILE_MS = 0.3       
BLOCAGE_MAX_S = 20.0          

SEUIL_FREINAGE_EVT = 0.1      

TOLERANCE_ARRIVEE_M = 12.0
FRACTION_MIN_AVANT_ARRIVEE = 0.5    

FACTEUR_DUREE_MAX = 5.0
MARGE_DUREE_S = 60.0


def _itineraire(carte, depart, distance_cible_m: float, pas_m: float = 2.0, direction: str = "tout_droit"):
    import carla
    wp = carte.get_waypoint(depart.location, project_to_road=True, lane_type=carla.LaneType.Driving)
    if wp is None: return []

    points = [wp]
    parcouru = 0.0
    while parcouru < distance_cible_m:
        suivants = wp.next(pas_m)
        if not suivants: break
        
        choix = suivants[0]
        if len(suivants) > 1:
            yaw_actuel = wp.transform.rotation.yaw
            for s in suivants:
                trace = s
                for _ in range(5):
                    nxt = trace.next(2.0)
                    if nxt: trace = nxt[0]
                    else: break
                diff = (trace.transform.rotation.yaw - yaw_actuel + 180) % 360 - 180
                if direction == "droite" and diff > 10: choix = s; break
                elif direction == "gauche" and diff < -10: choix = s; break
                elif direction == "tout_droit" and abs(diff) <= 10: choix = s; break
        
        wp = choix
        points.append(wp)
        parcouru += pas_m
    return points


def _appliquer_profil_tm(tm, vehicules, profil: str, ego_id: int) -> None:
    for v in vehicules:
        if getattr(v, "id", None) == ego_id: continue
        if profil == "gestionnaire": continue
        if profil == "strict":
            tm.ignore_lights_percentage(v, 0.0)
            tm.ignore_signs_percentage(v, 0.0)
            tm.ignore_vehicles_percentage(v, 0.0)
            tm.distance_to_leading_vehicle(v, 5.0)
            tm.auto_lane_change(v, False)
        elif profil == "agressif":
            tm.ignore_lights_percentage(v, 40.0)
            tm.ignore_signs_percentage(v, 40.0)
            tm.ignore_vehicles_percentage(v, 15.0)
            tm.distance_to_leading_vehicle(v, 1.0)
            tm.auto_lane_change(v, True)


def _resoudre_profil_tm(profil_arg: str, scenario: int) -> str:
    if profil_arg != "auto": return profil_arg
    return "agressif" if scenario == 4 else "strict"


def _ajuster_verdict_perception(verdict, percus_bruts, itineraire, carte, pos, tf, t_sim, v_ms):
    ego_wp = carte.get_waypoint(pos)
    ego_right = tf.get_right_vector()
    fwd = tf.get_forward_vector()

    dist_devant = 999.0
    v_devant_ms = 0.0

    for (acteur, _type, _angle), ag_risk in zip(percus_bruts, verdict.details):
        loc = acteur.get_transform().location
        vec = loc - pos
        real_dist = loc.distance(pos)
        offset_lateral = abs(vec.x * ego_right.x + vec.y * ego_right.y)
        devant = (fwd.x * vec.x + fwd.y * vec.y) > 0

        sur_itineraire = any(
            loc.distance(p.transform.location) < TOLERANCE_SUR_ITINERAIRE_M
            for p in itineraire[:HORIZON_ITINERAIRE_PTS]
        )

        menace = True
        is_oncoming = False

        if t_sim < DELAI_GRACE_SPAWN_S:
            menace = False
        elif "walker" in acteur.type_id:
            if not sur_itineraire and offset_lateral >= SEUIL_LATERAL_PIETON_M:
                menace = False
            elif devant and offset_lateral < SEUIL_LATERAL_PIETON_M:
                if real_dist < dist_devant:
                    dist_devant = real_dist
                    vv = acteur.get_velocity()
                    v_devant_ms = math.hypot(vv.x, vv.y)
        elif "vehicle" in acteur.type_id:
            act_wp = carte.get_waypoint(loc)
            meme_voie = (act_wp and ego_wp and act_wp.road_id == ego_wp.road_id and act_wp.lane_id == ego_wp.lane_id)

            closest_wp = min(itineraire[:HORIZON_ITINERAIRE_PTS], key=lambda p: loc.distance(p.transform.location)) if itineraire else ego_wp
            wp_yaw = closest_wp.transform.rotation.yaw
            act_yaw = acteur.get_transform().rotation.yaw
            diff_angle = abs((act_yaw - wp_yaw + 180) % 360 - 180)
            aligne_avec_voie = diff_angle < SEUIL_ALIGNEMENT_VOIE_DEG
            
            is_oncoming = diff_angle > 135.0
            valide_pour_acc = meme_voie or (sur_itineraire and aligne_avec_voie)

            futur_sur_itineraire = False
            vv = acteur.get_velocity()
            v_acteur = math.hypot(vv.x, vv.y)
            
            if not meme_voie and not sur_itineraire and v_acteur > 1.0 and not is_oncoming:
                for t_proj in [1.0, 2.0, 3.0]:
                    fx = loc.x + vv.x * t_proj
                    fy = loc.y + vv.y * t_proj
                    for p in itineraire[:HORIZON_ITINERAIRE_PTS]:
                        if math.hypot(fx - p.transform.location.x, fy - p.transform.location.y) < TOLERANCE_SUR_ITINERAIRE_M + 1.0:
                            futur_sur_itineraire = True
                            break
                    if futur_sur_itineraire: break

            if not meme_voie and not sur_itineraire and not futur_sur_itineraire:
                menace = False
            elif devant:
                if (valide_pour_acc and offset_lateral < SEUIL_LATERAL_VEHICULE_M and real_dist < dist_devant):
                    dist_devant = real_dist
                    v_devant_ms = v_acteur
                if real_dist > DIST_IGNORE_LOIN_M and (ag_risk.ttc > TTC_IGNORE_S or math.isinf(ag_risk.ttc)):
                    menace = False
                if (real_dist < DIST_IGNORE_ARRET_M and v_ms < SEUIL_ARRET_MS and v_acteur < SEUIL_ARRET_MS):
                    menace = False
            elif not sur_itineraire:
                menace = False

        if not menace and "vehicle" in acteur.type_id and real_dist < RAYON_CONVERGENCE_M:
            if not is_oncoming: 
                vv = acteur.get_velocity()
                ex = pos.x - loc.x
                ey = pos.y - loc.y
                nrm = math.hypot(ex, ey) or 1.0
                v_vers_ego = (vv.x * ex + vv.y * ey) / nrm
                if v_vers_ego > SEUIL_APPROCHE_MS:
                    menace = True

        if not menace:
            ag_risk.level = RiskLevel.SAFE

    if verdict.details:
        pire_ag = max(verdict.details, key=lambda d: d.level)
        verdict.level = pire_ag.level
        verdict.agent_critique = pire_ag.agent
    else:
        verdict.level = RiskLevel.SAFE
        verdict.agent_critique = None

    return dist_devant, v_devant_ms


def _proximite_critique(world, ego, rayon_m, demi_largeur_m):
    ego_tf = ego.get_transform()
    ego_loc = ego_tf.location
    fwd = ego_tf.get_forward_vector()
    right = ego_tf.get_right_vector()
    ego_id = ego.id
    
    yaw_ego = ego_tf.rotation.yaw

    proche = False
    dmin = float("inf")
    motif = ""
    for v in world.get_actors().filter('*vehicle*'):
        if v.id == ego_id: continue
        loc = v.get_transform().location
        dx = loc.x - ego_loc.x
        dy = loc.y - ego_loc.y
        d = math.hypot(dx, dy)
        if d >= rayon_m: continue
        
        lon = fwd.x * dx + fwd.y * dy
        lat = abs(right.x * dx + right.y * dy)
        
        yaw_act = v.get_transform().rotation.yaw
        diff_yaw = abs((yaw_act - yaw_ego + 180) % 360 - 180)
        is_oncoming = diff_yaw > 135.0

        cas = ""
        if d < DIST_CONTACT_M and lon > -0.3 * max(d, 0.01):
            cas = "contact"
        elif lon > 0 and lat < demi_largeur_m:
            cas = "couloir"
        elif lon > -DIST_CONTACT_M and not is_oncoming:
            vv = v.get_velocity()
            ego_v = ego.get_velocity()
            for t_proj in [0.5, 1.0, 1.5, 2.0]:
                fx = loc.x + vv.x * t_proj
                fy = loc.y + vv.y * t_proj
                ex_proj = ego_loc.x + ego_v.x * t_proj
                ey_proj = ego_loc.y + ego_v.y * t_proj
                if math.hypot(fx - ex_proj, fy - ey_proj) < DIST_PROXIMITE_CRITIQUE_M:
                    cas = "collision_imminente"
                    break

        if cas:
            proche = True
            if d < dmin:
                dmin = d
                motif = cas
    return proche, (dmin if proche else None), motif


def _feu_rouge_devant(world, ego, rayon_m):
    ego_tf = ego.get_transform()
    ego_loc = ego_tf.location
    fwd = ego_tf.get_forward_vector()
    for feu in world.get_actors().filter('*traffic_light*'):
        loc = feu.get_transform().location
        dx = loc.x - ego_loc.x
        dy = loc.y - ego_loc.y
        d = math.hypot(dx, dy)
        if d >= rayon_m: continue
        if (fwd.x * dx + fwd.y * dy) <= 0: continue
        try:
            import carla
            if feu.get_state() == carla.TrafficLightState.Red: return True
        except Exception: pass
    return False


def _nettoyer_detecteur(det) -> None:
    if det is None: return
    for nom in ("detruire", "destroy", "nettoyer", "stop"):
        fn = getattr(det, nom, None)
        if callable(fn):
            try: fn()
            except Exception: pass
            return


def main() -> int:
    parser = argparse.ArgumentParser(description="Trajet A -> B, banc d'essai CARLA V8.")
    parser.add_argument("--carte", default="Town03")
    parser.add_argument("--distance", type=float, default=400.0)
    parser.add_argument("--vitesse", type=float, default=50.0)
    parser.add_argument("--tick", type=int, default=20)
    parser.add_argument("--scenario", type=int, default=1, choices=[1, 2, 3, 4])
    parser.add_argument("--profil-tm", default="auto", choices=["auto", "gestionnaire", "strict", "agressif"])
    parser.add_argument("--direction", default="droite", choices=["tout_droit", "gauche", "droite"])
    parser.add_argument("--feu-rouge-s", type=float, default=FEU_ROUGE_S)
    parser.add_argument("--dist-arret", type=float, default=DIST_ARRET_M)
    parser.add_argument("--dist-reprise", type=float, default=DIST_REPRISE_M)
    parser.add_argument("--dist-suivi", type=float, default=DIST_SUIVI_M)
    parser.add_argument("--proximite-critique", type=float, default=DIST_PROXIMITE_CRITIQUE_M)
    parser.add_argument("--demi-largeur-couloir", type=float, default=DEMI_LARGEUR_COULOIR_M)
    parser.add_argument("--blocage-max-s", type=float, default=BLOCAGE_MAX_S)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--spawn-index", type=int, default=30)
    parser.add_argument("--no-hud", action="store_true")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=2000)
    # NOUVEAU : Seuils dynamiques pour le Grid Search
    parser.add_argument("--ttc-watch", type=float, default=2.0)
    parser.add_argument("--ci-danger", type=float, default=0.6)
    parser.add_argument("--drac-danger", type=float, default=6.0)
    args = parser.parse_args()

    global RiskLevel 
    from risk_engine import Geometrie, RiskLevel, RiskConfig, ScenarioContext, TypeRoute, assess_risk, commande_recommandee, ObsAgent, recommander
    from risk_engine.context import EtatRoute, Heure, Meteo
    from world.carla_bridge import CarlaBridge, _vitesse_ms
    from world.env_sensors import DetecteurCollision, contexte_route
    from world.traffic import GestionnaireTrafic
    from world.perception_oracle import acteurs_percus, contexte_depuis_perception

    profil_tm = _resoudre_profil_tm(args.profil_tm, args.scenario)

    print("=" * 62)
    print(f"  BENCHMARK V8 (OPTIMISATION) - scenario {args.scenario} | TM: {profil_tm}")
    print(f"  -> Distance: {args.distance} m | Dir: {args.direction.upper()}")
    print("=" * 62)

    ctx_base = ScenarioContext(
        vitesse_ego_kmh=args.vitesse, type_route=TypeRoute.URBAIN,
        geometrie=Geometrie.DROITE, limite_vitesse_kmh=int(args.vitesse),
        zone_travaux=False, etat_route=EtatRoute.SEC, meteo=Meteo.CLAIR,
        heure=Heure.JOUR, visibilite_m=800.0, agents=[],
    )

    dt = 1.0 / args.tick
    hud = None
    camera_image = None
    camera_actor = None
    det_collision = None
    trafic = None

    if not args.no_hud:
        from world.hud import HUD, HUDState
        hud = HUD(largeur=1280, hauteur=720)
        hud.demarrer()
        hud.cadence_hz = args.tick
    else:
        HUDState = None

    def _on_camera(image):
        import numpy as np
        arr = np.frombuffer(image.raw_data, dtype=np.uint8)
        arr = arr.reshape((image.height, image.width, 4))[:, :, :3][:, :, ::-1]
        nonlocal camera_image
        camera_image = arr.copy()

    log_dir = _ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"benchmark_v8_sc{args.scenario}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    log_file = open(log_path, "w", newline="", encoding="utf-8")
    log = csv.writer(log_file)
    log.writerow(["t", "distance_parcourue_m", "vitesse_kmh", "niveau", "n_agents_percus", "raison_arret", "recommandation"])

    niveau_max = RiskLevel.SAFE
    distance_parcourue = 0.0
    arrive = False
    t_sim = 0.0
    n_freinages = 0
    frein_actif_prec = False
    ego_en_attente = False
    temps_immobile = 0.0
    statut_fin = "timeout"

    try:
        with CarlaBridge(host=args.host, port=args.port, fixed_delta_seconds=dt) as pont:
            pont.charger_carte(args.carte)
            import carla
            import random

            for feu in pont.world.get_actors().filter('*traffic_light*'):
                feu.set_red_time(args.feu_rouge_s)
                feu.set_green_time(FEU_VERT_S)
                feu.set_yellow_time(FEU_JAUNE_S)

            random.seed(args.seed)
            carte = pont.world.get_map()
            spawns = carte.get_spawn_points()

            idx = args.spawn_index if len(spawns) > args.spawn_index else 0
            depart = spawns[idx]
            depart.location.z += 2.0

            itineraire = _itineraire(carte, depart, args.distance, direction=args.direction)
            arrivee = itineraire[-1].transform.location if itineraire else depart.location

            bpl = pont.world.get_blueprint_library()
            bp_ego = (bpl.filter("vehicle.tesla.model3") or bpl.filter("vehicle.*"))[0]
            bp_ego.set_attribute("role_name", "ego")
            pont.ego = pont.world.spawn_actor(bp_ego, depart)
            pont._ctx_base = ctx_base
            pont.world.tick()

            from world.weather import weather_params
            pont.world.set_weather(carla.WeatherParameters(**weather_params(ctx_base)))

            bp_cam = bpl.find("sensor.camera.rgb")
            bp_cam.set_attribute("image_size_x", "960")
            bp_cam.set_attribute("image_size_y", "540")
            bp_cam.set_attribute("fov", "90")
            cam_tf = carla.Transform(carla.Location(x=-4.5, z=2.5), carla.Rotation(pitch=-10.0))
            camera_actor = pont.world.spawn_actor(bp_cam, cam_tf, attach_to=pont.ego)
            camera_actor.listen(_on_camera)

            det_collision = DetecteurCollision(pont.world, pont.ego)
            trafic = GestionnaireTrafic(pont.world, pont.tm, scenario_id=args.scenario)
            trafic.spawn_autour_de(pont.ego, rayon_m=args.distance + 100.0, centre=depart.location)

            _appliquer_profil_tm(pont.tm, pont.world.get_actors().filter('*vehicle*'), profil_tm, pont.ego.id)

            print("\n-> Depart du Benchmark V8.")
            t_sim = 0.0
            pos_prec = pont.ego.get_transform().location
            duree_max = args.distance / max(args.vitesse / 3.6, 1.0) * FACTEUR_DUREE_MAX + MARGE_DUREE_S

            while t_sim < duree_max:
                if hud is not None:
                    hud.gerer_evenements()
                    if not hud.actif(): break
                    if hud.en_pause():
                        pont.ego.apply_control(carla.VehicleControl(brake=1.0))
                        continue

                pont.tick()
                t_sim += dt
                trafic.tick(t_sim)
                det_collision.maj_temps(t_sim)

                tf = pont.ego.get_transform()
                pos = tf.location
                distance_parcourue += pos.distance(pos_prec)
                pos_prec = pos
                v_ms = _vitesse_ms(pont.ego)
                fwd = tf.get_forward_vector()
                ego_right = tf.get_right_vector()

                while itineraire and pos.distance(itineraire[0].transform.location) < max(2.5, v_ms):
                    itineraire.pop(0)

                cr = contexte_route(pont.world, pont.ego)
                ctx_courant = replace(ctx_base, limite_vitesse_kmh=cr.limite_vitesse_kmh, geometrie=cr.geometrie)

                percus_bruts = acteurs_percus(pont.world, pont.ego, rayon_m=RAYON_PERCEPTION_M, demi_angle_deg=DEMI_ANGLE_PERCEPTION_DEG)
                ctx_t = contexte_depuis_perception(ctx_courant, pont.ego, percus_bruts)

                # Instanciation de la configuration avec les seuils dynamiques
                cfg = RiskConfig(
                    ttc_watch=args.ttc_watch,
                    ci_danger=args.ci_danger,
                    drac_danger=args.drac_danger
                )
                verdict = assess_risk(ctx_t, cfg=cfg)

                dist_devant, v_devant_ms = _ajuster_verdict_perception(verdict, percus_bruts, itineraire, carte, pos, tf, t_sim, v_ms)
                reco = recommander(ctx_t, verdict)

                agents_pour_hud = []
                dict_critique = None
                metriques_dict = {}
                pire_ag = None

                if verdict.details:
                    if verdict.agent_critique:
                        pire_ag = next(d for d in verdict.details if d.agent == verdict.agent_critique)
                        dict_critique = {
                            "niveau": pire_ag.level, "type": pire_ag.agent.type_agent.value, "distance": pire_ag.agent.distance_m,
                            "ttc": pire_ag.ttc_effectif if pire_ag.ttc_effectif != float('inf') else None, "drac": pire_ag.drac,
                        }
                        metriques_dict = {
                            "TTC": (pire_ag.ttc if pire_ag.ttc != float('inf') else None, "s", pire_ag.niveaux.get("TTC", RiskLevel.SAFE)),
                            "THW": (pire_ag.thw if pire_ag.thw != float('inf') else None, "s", pire_ag.niveaux.get("THW", RiskLevel.SAFE)),
                            "PET": (pire_ag.pet if pire_ag.pet != float('inf') else None, "s", pire_ag.niveaux.get("PET", RiskLevel.SAFE)),
                            "RSS": (pire_ag.rss_min, "m", pire_ag.niveaux.get("RSS", RiskLevel.SAFE)),
                            "CI": (pire_ag.ci, "", pire_ag.niveaux.get("CI", RiskLevel.SAFE)),
                            "DRAC": (pire_ag.drac, "m/s²", pire_ag.niveaux.get("DRAC", RiskLevel.SAFE)),
                        }

                for ag_risk in verdict.details:
                    dist = ag_risk.agent.distance_m
                    ecart = ag_risk.agent.ecart_lateral_m
                    x_rel = math.sqrt(max(0.0, dist**2 - ecart**2))
                    agents_pour_hud.append({
                        "niveau": ag_risk.level, "type": ag_risk.agent.type_agent.value, "distance": dist,
                        "ttc": ag_risk.ttc_effectif if ag_risk.ttc_effectif != float('inf') else None,
                        "drac": ag_risk.drac, "dx_relatif": x_rel, "dy_relatif": ecart,
                    })

                obs = [ObsAgent(x=a.get_transform().location.x, y=a.get_transform().location.y, drac=d.drac) for (a, _, _), d in zip(percus_bruts, verdict.details)]
                cmd = commande_recommandee(verdict, ctx_t, pos.x, pos.y, obs)

                feu_rouge = False
                etat_feu_str = "aucun"
                if pont.ego.is_at_traffic_light():
                    etat_feu = pont.ego.get_traffic_light_state()
                    if etat_feu == carla.TrafficLightState.Red: feu_rouge = True; etat_feu_str = "rouge"
                    elif etat_feu == carla.TrafficLightState.Yellow: etat_feu_str = "jaune"
                    elif etat_feu == carla.TrafficLightState.Green: etat_feu_str = "vert"

                d_look = max(D_LOOK_MIN_M, min(D_LOOK_MAX_M, v_ms * D_LOOK_GAIN))
                wp_cible = None
                for p in itineraire:
                    if p.transform.location.distance(pos) > d_look: wp_cible = p; break
                if not wp_cible and itineraire: wp_cible = itineraire[-1]

                steer_val = 0.0
                facteur_courbe = 1.0
                if wp_cible:
                    vec_cible = wp_cible.transform.location - pos
                    x_local = vec_cible.x * fwd.x + vec_cible.y * fwd.y
                    y_local = vec_cible.x * ego_right.x + vec_cible.y * ego_right.y
                    angle_cible = math.atan2(y_local, x_local)
                    gain_steer = GAIN_STEER_LENT if v_ms < SEUIL_V_LENTE_MS else GAIN_STEER_RAPIDE
                    steer_val = max(-1.0, min(1.0, angle_cible * gain_steer))
                    facteur_courbe = max(FACTEUR_COURBE_MIN, 1.0 - abs(angle_cible))

                v_lim_ms = args.vitesse / 3.6
                v_cible = v_lim_ms * facteur_courbe
                if etat_feu_str == "jaune": v_cible = min(v_cible, V_JAUNE_MS)
                if dist_devant < args.dist_suivi: v_cible = min(v_cible, v_devant_ms)

                if dist_devant < args.dist_arret: ego_en_attente = True
                elif dist_devant > args.dist_reprise: ego_en_attente = False
                if ego_en_attente: v_cible = 0.0
                if feu_rouge: v_cible = 0.0

                proche_critique, dist_critique, motif_critique = _proximite_critique(pont.world, pont.ego, args.proximite_critique, args.demi_largeur_couloir)
                if proche_critique: v_cible = 0.0

                feu_devant = _feu_rouge_devant(pont.world, pont.ego, RAYON_FEU_DEVANT_M)

                suivi_arrete = (dist_devant < args.dist_suivi and v_devant_ms < SEUIL_ARRET_MS)
                if proche_critique: raison_arret = f"proximite:{motif_critique}"
                elif feu_rouge: raison_arret = "feu_rouge"
                elif (ego_en_attente or suivi_arrete) and feu_devant: raison_arret = "feu_rouge_devant"
                elif ego_en_attente: raison_arret = "attente_vehicule"
                elif suivi_arrete: raison_arret = "suivi_vehicule_arrete"
                elif cmd.mode != "nominal": raison_arret = f"moteur:{cmd.mode}"
                else: raison_arret = ""

                throttle = 0.0
                brake = 0.0
                mode_actuel = cmd.mode

                # --- CORRECTION V8 ICI ---
                if feu_rouge:
                    brake = max(cmd.brake, _frein_pour_vcible(v_cible, v_ms))
                    if verdict.level == RiskLevel.SAFE: reco = replace(reco, message="SAFE : arret au feu rouge")
                
                # On n'écoute les injonctions du moteur QUE s'il y a un vrai danger détecté (!= SAFE)
                elif cmd.mode != "nominal" and verdict.level != RiskLevel.SAFE:
                    throttle = cmd.throttle
                    brake = cmd.brake
                    if brake > 0.0 and v_ms < SEUIL_ARRET_MS: brake = 1.0; throttle = 0.0
                
                # Si le verdict est SAFE, l'ACC (le script) prend le contrôle pour fluidifier la conduite
                else:
                    delta_v = v_cible - v_ms
                    if v_cible < V_CIBLE_NULLE_MS and v_ms < 1.0: brake = 1.0
                    elif delta_v > DEADBAND_V_MS: throttle = min(0.7, delta_v * 0.4)
                    elif delta_v < -DEADBAND_V_MS: brake = min(BRAKE_MAX, -delta_v / max(v_ms, 1.0))

                # Le garde-fou d'urgence mécanique reste prioritaire
                if proche_critique: throttle = 0.0; brake = 1.0

                if int(verdict.level) > int(niveau_max): niveau_max = verdict.level

                frein_actif = brake > SEUIL_FREINAGE_EVT
                if frein_actif and not frein_actif_prec: n_freinages += 1
                frein_actif_prec = frein_actif

                pont.ego.apply_control(carla.VehicleControl(throttle=throttle, brake=brake, steer=steer_val))

                justifie_par_feu = feu_rouge or feu_devant
                if v_ms >= SEUIL_IMMOBILE_MS: temps_immobile = 0.0
                elif not justifie_par_feu: temps_immobile += dt

                log.writerow([f"{t_sim:.2f}", f"{distance_parcourue:.1f}", f"{v_ms*3.6:.1f}", verdict.level.name, len(percus_bruts), raison_arret, reco.message])

                if temps_immobile > args.blocage_max_s:
                    print(f"\n[BLOC] BLOCAGE : ego immobile {temps_immobile:.1f}s (raison: {raison_arret or 'inconnue'}). Abandon.")
                    statut_fin = "bloque"
                    break

                if hud is not None:
                    hud.attacher_image_camera(camera_image)
                    hud.rendre(HUDState(
                        t=t_sim, niveau=verdict.level, vitesse_ego_kmh=v_ms * 3.6, freinage=brake > 0.05,
                        agent_critique=dict_critique, metriques=metriques_dict, metrique_decisive=pire_ag.metrique_decisive if pire_ag else "",
                        ratio_rss=pire_ag.ratio_rss if pire_ag and pire_ag.ratio_rss != float('inf') else None,
                        ttc_effectif=pire_ag.ttc_effectif if pire_ag and pire_ag.ttc_effectif != float('inf') else None,
                        marge_contextuelle=pire_ag.marge if pire_ag else None, corroboration=pire_ag.corroboration if pire_ag else None,
                        n_agents=len(percus_bruts), diagnostic=f"{reco.message} | {distance_parcourue:.0f}/{args.distance:.0f} m",
                        mu_g=cmd.mu_g, mode_ctrl=mode_actuel, v_cible_kmh=v_cible * 3.6, limite_vitesse_kmh=cr.limite_vitesse_kmh,
                        geometrie=cr.geometrie.value, feu=etat_feu_str, hors_voie=cr.hors_voie,
                        n_collisions=det_collision.nombre, collision_recente=det_collision.collision_recente(),
                        mode_conduite="libre", agents_detail=agents_pour_hud, rayon_perception_m=RAYON_PERCEPTION_M, demi_angle_perception_deg=DEMI_ANGLE_PERCEPTION_DEG,
                    ))

                if (distance_parcourue > args.distance * FRACTION_MIN_AVANT_ARRIVEE and pos.distance(arrivee) < TOLERANCE_ARRIVEE_M):
                    print("\n[OK] POINT B ATTEINT : fin de la simulation.")
                    arrive = True; statut_fin = "arrive"
                    break

                if distance_parcourue >= args.distance:
                    print("\n[OK] DISTANCE CIBLE PARCOURUE : fin de la simulation.")
                    arrive = True; statut_fin = "arrive"
                    break

            if statut_fin == "timeout": print("\n[WARN] Fin par timeout (duree_max atteinte).")

    except KeyboardInterrupt: pass
    except Exception as e:
        print(f"X Erreur critique : {e}")
        import traceback
        traceback.print_exc()
    finally:
        # --- PRIORITÉ ABSOLUE : écrire le résumé AVANT tout nettoyage. ---
        # Le nettoyage CARLA (trafic, sensors, TrafficManager) peut planter
        # nativement à la fermeture sous Windows (0xC0000409, tue le process
        # sans exception Python). Un résumé écrit après ce nettoyage est perdu.
        # On l'écrit ici, puis on procède au nettoyage.
        n_collisions = det_collision.nombre if det_collision else 0
        vitesse_moy_kmh = (distance_parcourue / t_sim * 3.6) if t_sim > 0 else 0.0
        resume_path = log_path.with_name(log_path.stem + "_resume.csv")
        try:
            with open(resume_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["scenario", "ttc_watch", "ci_danger", "drac_danger", "profil_tm", "seed", "statut_fin", "arrive", "temps_arrivee_s", "vitesse_moyenne_kmh", "distance_parcourue_m", "n_collisions", "n_freinages", "niveau_max"])
                w.writerow([args.scenario, args.ttc_watch, args.ci_danger, args.drac_danger, profil_tm, args.seed, statut_fin, int(arrive), f"{t_sim:.2f}", f"{vitesse_moy_kmh:.2f}", f"{distance_parcourue:.1f}", n_collisions, n_freinages, niveau_max.name])
                f.flush()
                os.fsync(f.fileno())    # garantit que la ligne est sur le disque
        except Exception as e:
            print(f"! Ecriture du resume impossible : {e}")

        print(f"-> Resume       : {resume_path}")
        print(f"-> Statut={statut_fin} | t={t_sim:.1f}s | v_moy={vitesse_moy_kmh:.1f} km/h | collisions={n_collisions} | freinages={n_freinages} | niveau_max={niveau_max.name}")

        # --- Nettoyage (best-effort, peut planter nativement) ---
        try:
            if trafic is not None: trafic.nettoyer()
        except Exception: pass
        if camera_actor:
            try: camera_actor.stop()
            except Exception: pass
            try: camera_actor.destroy()
            except Exception: pass
        _nettoyer_detecteur(det_collision)
        if hud: hud.fermer()
        log_file.close()
        print(f"-> Journal      : {log_path}")

    return 0 if arrive else 1


def _frein_pour_vcible(v_cible: float, v_ms: float) -> float:
    delta_v = v_cible - v_ms
    if delta_v >= -DEADBAND_V_MS: return 0.0
    if v_cible < V_CIBLE_NULLE_MS and v_ms < 1.0: return 1.0
    return min(BRAKE_MAX, -delta_v / max(v_ms, 1.0))


if __name__ == "__main__":
    sys.exit(main())
