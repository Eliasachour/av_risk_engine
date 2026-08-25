"""
Rejouabilité des scenarios de reference (SC-XX) dans CARLA.

Cette étape 4 permet de :
  1. Rejouer un scénario de référence donné dans CARLA (mêmes agents, mêmes
     conditions, position spawn contrôlée).
  2. Enregistrer le comportement observé (niveaux atteints, TTC minimal,
     collision ou non) dans un log CSV.
  3. **Comparer** ce comportement au verdict prédit par le moteur en amont
     (calibration hors ligne).

C'est ce qui permet de dire, en soutenance : « le moteur prédit CRITICAL pour
SC-05 en simulateur cinématique. Rejoué dans CARLA, on observe effectivement
un niveau CRITICAL atteint à t=1.8s, avec une distance minimale de 2.3m. »

Usage :
    python carla_replay.py --preset SC-05 --duree 15
    python carla_replay.py --all --duree 20 --headless   # rejouer tous les 24

Le mode --headless désactive le HUD Pygame pour un run rapide en batch.
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


import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ResultatRejeu:
    """Bilan d'un scénario rejoué dans CARLA.

    La comparaison est faite à QUATRE colonnes, et pas deux, parce que
    comparer une étiquette décrivant l'instant initial au maximum atteint sur
    plusieurs secondes de simulation n'a pas de sens : l'ego roule vers le
    conflit, donc presque tout scénario finit par devenir CRITICAL.

    - ``niveau_attendu``    : l'étiquette de calibration, qui décrit t = 0 ;
    - ``niveau_hors_ligne`` : ce que le moteur produit sur le scénario
      cinématique, hors CARLA — la référence d'implémentation ;
    - ``niveau_t0_carla``   : ce que le moteur produit au premier tick CARLA.
      **C'est cette colonne qui se compare à l'étiquette** : même instant,
      même sémantique. L'écart mesure la fidélité du portage CARLA ;
    - ``niveau_max_carla``  : le pire niveau atteint sur toute la durée. Ne se
      compare pas à l'étiquette ; renseigne sur l'évolution du scénario.
    """
    id_scenario: str
    nom: str
    niveau_attendu: str
    niveau_hors_ligne: str
    niveau_t0_carla: str
    niveau_max_carla: str
    ttc_min: Optional[float]
    distance_min: Optional[float]
    collision: bool
    duree_s: float
    accord: bool                  # niveau_t0_carla == niveau_attendu ?
    fidelite: bool                # niveau_t0_carla == niveau_hors_ligne ?


def rejouer_scenario(preset_id: str, duree_max_s: float = 15.0,
                     tick_hz: int = 20, host: str = "localhost", port: int = 2000,
                     avec_hud: bool = True, carte: str = "Town04") -> ResultatRejeu:
    """Rejoue un scénario donné dans CARLA et renvoie le bilan."""
    from calibration.scenarios_ref import REFERENCES
    from risk_engine import assess_risk, commande_recommandee, ObsAgent
    from world.carla_bridge import CarlaBridge, _vitesse_ms

    ref = next((r for r in REFERENCES if r.id == preset_id), None)
    if ref is None:
        raise ValueError(f"Scenario inconnu : {preset_id}")

    ctx = ref.ctx
    print(f"→ Rejeu de {ref.id} — {ref.nom}")
    print(f"  Niveau attendu (calibration) : {ref.niveau_attendu.name}")
    print(f"  Ego : {ctx.vitesse_ego_kmh:.0f} km/h, {ctx.meteo.value}/{ctx.etat_route.value}")
    print(f"  {len(ctx.agents)} agent(s) a spawner")

    dt = 1.0 / tick_hz

    # Le HUD est optionnel (pratique pour --headless en batch)
    hud = None
    if avec_hud:
        from world.hud import HUD, HUDState
        hud = HUD(largeur=1280, hauteur=720)
        hud.demarrer()

    niveau_max_observe = "SAFE"
    niveau_t0: Optional[str] = None
    ttc_min_observe: Optional[float] = None
    distance_min_observe: Optional[float] = None
    collision_observee = False

    with CarlaBridge(host=host, port=port, fixed_delta_seconds=dt) as pont:
        pont.charger_carte(carte)
        pont.appliquer_scenario(ctx)

        import carla
        # Camera si HUD actif
        camera_image = None
        camera_actor = None
        if hud:
            def _on_camera(image):
                import numpy as np
                arr = np.frombuffer(image.raw_data, dtype=np.uint8)
                arr = arr.reshape((image.height, image.width, 4))[:, :, :3][:, :, ::-1]
                nonlocal camera_image
                camera_image = arr.copy()

            bp_cam = pont.world.get_blueprint_library().find("sensor.camera.rgb")
            bp_cam.set_attribute("image_size_x", "960")
            bp_cam.set_attribute("image_size_y", "540")
            cam_tf = carla.Transform(carla.Location(x=-4.5, z=2.5),
                                     carla.Rotation(pitch=-10.0))
            camera_actor = pont.world.spawn_actor(bp_cam, cam_tf, attach_to=pont.ego)
            camera_actor.listen(_on_camera)

        t_sim = 0.0
        while t_sim < duree_max_s:
            if hud:
                hud.gerer_evenements()
                if not hud.actif():
                    break

            pont.tick()
            t_sim += dt
            ctx_t = pont.contexte_courant()
            verdict = assess_risk(ctx_t)

            # Statistiques observées
            if niveau_t0 is None:
                niveau_t0 = verdict.level.name   # premier tick : comparable a l'etiquette
            if _rang(verdict.level.name) > _rang(niveau_max_observe):
                niveau_max_observe = verdict.level.name

            ttcs = [d.ttc for d in verdict.details if math.isfinite(d.ttc)]
            if ttcs:
                m = min(ttcs)
                if ttc_min_observe is None or m < ttc_min_observe:
                    ttc_min_observe = m

            ego_loc = pont.ego.get_transform().location
            for actor in pont.agents:
                loc = actor.get_transform().location
                d = math.hypot(loc.x - ego_loc.x, loc.y - ego_loc.y)
                if distance_min_observe is None or d < distance_min_observe:
                    distance_min_observe = d
                if d < 1.5:
                    collision_observee = True

            # Piloter l'ego (freinage automatique via commande_recommandee)
            v_ego_ms = _vitesse_ms(pont.ego)
            ego_tf = pont.ego.get_transform()
            obs = [
                ObsAgent(x=a.get_transform().location.x,
                         y=a.get_transform().location.y,
                         drac=d.drac)
                for a, d in zip(pont.agents, verdict.details)
            ]
            cmd = commande_recommandee(verdict, ctx_t, ego_tf.location.x, ego_tf.location.y, obs)
            # Reprise ACC + pilotage lateral simple
            v_cible = ctx.vitesse_ego_kmh / 3.6
            throttle = cmd.throttle
            brake = cmd.brake
            if cmd.mode == "nominal" and v_ego_ms < v_cible - 0.5:
                throttle = min((v_cible - v_ego_ms) / v_cible, 0.6)
            # Steer simple (garde en voie)
            from world.carla_control import pilotage_lateral
            steer = pilotage_lateral(pont, ego_tf, v_ego_ms)
            pont.ego.apply_control(carla.VehicleControl(
                throttle=throttle, brake=brake, steer=steer,
            ))

            if hud:
                agents_detail = []
                for detail, actor in zip(verdict.details, pont.agents):
                    loc = actor.get_transform().location
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
                ac = max(agents_detail, key=lambda a: _rang(a["niveau"].name), default=None)
                hud.attacher_image_camera(camera_image)
                hud.rendre(HUDState(
                    t=t_sim, niveau=verdict.level, vitesse_ego_kmh=v_ego_ms * 3.6,
                    freinage=brake > 0.05, agent_critique=ac,
                    n_agents=len(pont.agents),
                    diagnostic=f"Rejeu {ref.id} - {cmd.mode}",
                    mu_g=cmd.mu_g, mode_ctrl=cmd.mode,
                    agents_detail=agents_detail, v_cible_kmh=ctx.vitesse_ego_kmh,
                ))

            if collision_observee:
                print(f"  ✗ Collision detectee a t={t_sim:.1f}s")
                break

        if camera_actor and camera_actor.is_alive:
            camera_actor.destroy()

    if hud:
        hud.fermer()

    # Niveau hors ligne : le moteur sur le scenario cinematique, sans CARLA.
    niveau_hors_ligne = assess_risk(ctx).level.name
    niveau_t0 = niveau_t0 or "SAFE"

    return ResultatRejeu(
        id_scenario=ref.id, nom=ref.nom,
        niveau_attendu=ref.niveau_attendu.name,
        niveau_hors_ligne=niveau_hors_ligne,
        niveau_t0_carla=niveau_t0,
        niveau_max_carla=niveau_max_observe,
        ttc_min=ttc_min_observe,
        distance_min=distance_min_observe,
        collision=collision_observee,
        duree_s=t_sim,
        accord=(niveau_t0 == ref.niveau_attendu.name),
        fidelite=(niveau_t0 == niveau_hors_ligne),
    )


def _rang(n: str) -> int:
    return {"SAFE": 0, "WATCH": 1, "DANGER": 2, "CRITICAL": 3}.get(n, 0)


def _ecrire_bilan(resultats: List[ResultatRejeu], chemin: Path) -> None:
    """Écrit le bilan de tous les rejeux dans un CSV."""
    chemin.parent.mkdir(exist_ok=True, parents=True)
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "id", "nom", "niveau_attendu", "niveau_hors_ligne",
            "niveau_t0_carla", "niveau_max_carla",
            "accord_etiquette", "fidelite_portage",
            "ttc_min_s", "distance_min_m", "collision", "duree_s"
        ])
        for r in resultats:
            w.writerow([
                r.id_scenario, r.nom, r.niveau_attendu, r.niveau_hors_ligne,
                r.niveau_t0_carla, r.niveau_max_carla,
                "oui" if r.accord else "non",
                "oui" if r.fidelite else "non",
                f"{r.ttc_min:.2f}" if r.ttc_min is not None else "",
                f"{r.distance_min:.2f}" if r.distance_min is not None else "",
                "oui" if r.collision else "non",
                f"{r.duree_s:.1f}",
            ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Rejeu des scenarios de reference SC-XX dans CARLA.")
    parser.add_argument("--preset", type=str, help="ID d'un scenario (ex: SC-05)")
    parser.add_argument("--all", action="store_true", help="Rejouer les 24 scenarios en batch")
    parser.add_argument("--duree", type=float, default=15.0, help="Duree max par scenario (s)")
    parser.add_argument("--carte", type=str, default="Town04")
    parser.add_argument("--headless", action="store_true", help="Sans HUD (batch rapide)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=2000)
    args = parser.parse_args()

    if not args.preset and not args.all:
        print("Precisez --preset SC-XX ou --all")
        return 1

    resultats: List[ResultatRejeu] = []
    try:
        if args.all:
            from calibration.scenarios_ref import REFERENCES
            for ref in REFERENCES:
                try:
                    r = rejouer_scenario(ref.id, duree_max_s=args.duree,
                                          host=args.host, port=args.port,
                                          avec_hud=not args.headless, carte=args.carte)
                    resultats.append(r)
                    tag = "OK" if r.fidelite else "!="
                    print(f"  [{tag}] {r.id_scenario}: etiquette={r.niveau_attendu:9s} "
                          f"hors-ligne={r.niveau_hors_ligne:9s} "
                          f"CARLA t0={r.niveau_t0_carla:9s} max={r.niveau_max_carla}")
                except Exception as e:
                    print(f"  ! Echec sur {ref.id}: {e}")
        else:
            r = rejouer_scenario(args.preset, duree_max_s=args.duree,
                                  host=args.host, port=args.port,
                                  avec_hud=not args.headless, carte=args.carte)
            resultats.append(r)
    except KeyboardInterrupt:
        print("\n→ Interrompu par l'utilisateur")

    # Ecrire le bilan
    log_dir = Path("logs")
    log_path = log_dir / f"rejeu_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    _ecrire_bilan(resultats, log_path)
    print(f"\n→ Bilan ecrit : {log_path}")

    # Recap console
    if resultats:
        n = len(resultats)
        n_fid = sum(1 for r in resultats if r.fidelite)
        n_acc = sum(1 for r in resultats if r.accord)
        n_coll = sum(1 for r in resultats if r.collision)
        print()
        print(f"→ FIDELITE DU PORTAGE : {n_fid}/{n} (CARLA t0 == hors ligne)")
        print(f"    C'est LA mesure qui valide l'integration : le moteur doit")
        print(f"    produire le meme verdict quelle que soit la source des donnees.")
        print(f"→ Accord avec l'etiquette : {n_acc}/{n} (CARLA t0 == etiquette)")
        print(f"→ Collisions : {n_coll}/{n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
