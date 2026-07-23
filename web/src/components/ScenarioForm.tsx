import { useEffect, useState } from "react";
import type { ScenarioIn, AgentIn, Enums, Preset, RiskLevel, Contraintes } from "../types";
import { COULEURS_NIVEAU } from "../types";
import { api } from "../api";

interface Props {
  scenario: ScenarioIn;
  onChange: (s: ScenarioIn) => void;
  onSimulate: (reaction: boolean) => void;
  enums: Enums;
  onResetLayout?: () => void;
}

const num = (v: string, fallback = 0): number => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : fallback;
};

const AG_DEFAULT: AgentIn = {
  type_agent: "voiture",
  vitesse_kmh: 30,
  distance_m: 40,
  cap_relatif_deg: 0,
  acceleration_ms2: 0,
  ecart_lateral_m: 0,
  profondeur_mesuree: true,
};

export function ScenarioForm({ scenario, onChange, onSimulate, enums, onResetLayout }: Props) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [showPresets, setShowPresets] = useState(false);
  const [reaction, setReaction] = useState(true);
  const [ag, setAg] = useState<AgentIn>(AG_DEFAULT);
  const [contraintes, setContraintes] = useState<Contraintes | null>(null);

  useEffect(() => {
    api.presets().then(setPresets).catch(console.error);
    api.contraintes().then(setContraintes).catch(console.error);
  }, []);

  const set = <K extends keyof ScenarioIn>(k: K, v: ScenarioIn[K]) =>
    onChange({ ...scenario, [k]: v });

  // --- Cohérence entre paramètres (mêmes règles que scenarios/constraints.py) ---

  const etatsCompatibles: string[] =
    contraintes?.meteo_routes[scenario.meteo] ?? enums.etat_route;

  const limitesCompatibles: number[] = (() => {
    if (!contraintes) return [];
    const base = contraintes.limites_route[scenario.type_route] ?? [];
    if (!scenario.zone_travaux) return base;
    const mx = Math.max(...base);
    return [...new Set([...base, ...contraintes.zone_travaux_limites.filter((v) => v < mx)])]
      .sort((a, b) => a - b);
  })();

  const plageVis = (meteo: string, heure: string): [number, number] => {
    if (!contraintes) return [0, 1000];
    let [lo, hi] = contraintes.vis_meteo[meteo] ?? [0, 1000];
    if (heure === "nuit") { lo *= contraintes.facteur_nuit; hi *= contraintes.facteur_nuit; }
    return [lo, hi];
  };

  /** Change la météo en réalignant automatiquement l'état de route et la visibilité. */
  const setMeteo = (meteo: string) => {
    const compat = contraintes?.meteo_routes[meteo] ?? enums.etat_route;
    const etat = compat.includes(scenario.etat_route) ? scenario.etat_route : compat[0];
    const [lo, hi] = plageVis(meteo, scenario.heure);
    const vis = Math.min(Math.max(scenario.visibilite_m, lo), hi);
    onChange({ ...scenario, meteo, etat_route: etat, visibilite_m: Math.round(vis) });
  };

  /** Change l'heure en réajustant la visibilité dans la plage plausible. */
  const setHeure = (heure: string) => {
    const [lo, hi] = plageVis(scenario.meteo, heure);
    const vis = Math.min(Math.max(scenario.visibilite_m, lo), hi);
    onChange({ ...scenario, heure, visibilite_m: Math.round(vis) });
  };

  /** Change le type de route (ou zone travaux) en réalignant la limite. */
  const setRoute = (patch: Partial<ScenarioIn>) => {
    const next = { ...scenario, ...patch };
    if (contraintes) {
      const base = contraintes.limites_route[next.type_route] ?? [];
      let lims = base;
      if (next.zone_travaux) {
        const mx = Math.max(...base);
        lims = [...new Set([...base, ...contraintes.zone_travaux_limites.filter((v) => v < mx)])];
      }
      if (lims.length && !lims.includes(next.limite_vitesse_kmh)) {
        // choisir la limite plausible la plus proche
        next.limite_vitesse_kmh = lims.reduce((best, v) =>
          Math.abs(v - next.limite_vitesse_kmh) < Math.abs(best - next.limite_vitesse_kmh) ? v : best);
      }
    }
    onChange(next);
  };

  const addAgent = () => {
    onChange({ ...scenario, agents: [...scenario.agents, ag] });
    // Léger reset : conserver le type, remettre l'écart à 0 pour éviter les doublons involontaires
    setAg({ ...ag, ecart_lateral_m: 0 });
  };
  const rmAgent = (i: number) => set("agents", scenario.agents.filter((_, j) => j !== i));

  const loadPreset = async (id: string) => {
    const p = await api.preset(id);
    onChange(p.scenario);
    setShowPresets(false);
  };

  return (
    <div className="panel">
      <h2>Scénario</h2>

      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <button className="btn" style={{ flex: 1 }} onClick={() => setShowPresets(!showPresets)}>
          {showPresets ? "▾" : "▸"} Préréglages ({presets.length})
        </button>
        <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => onSimulate(reaction)}>
          ▶ Simuler
        </button>
      </div>

      <label className="checkbox" style={{ marginBottom: 10 }}>
        <input type="checkbox" checked={reaction} onChange={(e) => setReaction(e.target.checked)} />
        L'ego réagit (freine)
      </label>

      {showPresets && (
        <div className="preset-menu">
          {presets.map((p) => {
            const c = COULEURS_NIVEAU[p.niveau_attendu as RiskLevel];
            return (
              <div key={p.id} className="preset-item" onClick={() => loadPreset(p.id)}>
                <span><span className="id">{p.id}</span> — {p.nom}</span>
                <span className="n" style={{ background: c.bg, color: c.fg }}>{p.niveau_attendu}</span>
              </div>
            );
          })}
        </div>
      )}

      <h3>Route</h3>
      <div className="field">
        <label>Type de route</label>
        <select value={scenario.type_route} onChange={(e) => setRoute({ type_route: e.target.value })}>
          {enums.type_route.map((v) => <option key={v}>{v}</option>)}
        </select>
      </div>
      <div className="row-2">
        <div className="field">
          <label>Géométrie</label>
          <select value={scenario.geometrie} onChange={(e) => set("geometrie", e.target.value)}>
            {enums.geometrie.map((v) => <option key={v}>{v}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Limite (km/h)</label>
          {limitesCompatibles.length ? (
            <select value={scenario.limite_vitesse_kmh}
              onChange={(e) => set("limite_vitesse_kmh", num(e.target.value, 50))}>
              {limitesCompatibles.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          ) : (
            <input type="number" value={scenario.limite_vitesse_kmh}
              onChange={(e) => set("limite_vitesse_kmh", num(e.target.value))} />
          )}
        </div>
      </div>
      <label className="checkbox">
        <input type="checkbox" checked={scenario.zone_travaux}
          onChange={(e) => setRoute({ zone_travaux: e.target.checked })} />
        Zone de travaux
      </label>

      <h3>Environnement</h3>
      <div className="row-2">
        <div className="field">
          <label>Météo</label>
          <select value={scenario.meteo} onChange={(e) => setMeteo(e.target.value)}>
            {enums.meteo.map((v) => <option key={v}>{v}</option>)}
          </select>
        </div>
        <div className="field">
          <label>État route</label>
          <select value={scenario.etat_route} onChange={(e) => set("etat_route", e.target.value)}>
            {etatsCompatibles.map((v) => <option key={v}>{v}</option>)}
          </select>
        </div>
      </div>
      <div className="row-2">
        <div className="field">
          <label>Heure</label>
          <select value={scenario.heure} onChange={(e) => setHeure(e.target.value)}>
            {enums.heure.map((v) => <option key={v}>{v}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Visibilité (m)</label>
          <input type="number" value={scenario.visibilite_m}
            onChange={(e) => set("visibilite_m", num(e.target.value))} />
        </div>
      </div>

      <h3>Véhicule ego</h3>
      <div className="field">
        <label>Vitesse (km/h)</label>
        <input type="number" value={scenario.vitesse_ego_kmh}
          onChange={(e) => set("vitesse_ego_kmh", num(e.target.value))} />
      </div>

      <h3>Usagers ({scenario.agents.length})</h3>
      {scenario.agents.map((a, i) => (
        <div key={i} className="agent-item">
          <span className="mono">
            {a.type_agent} · v={a.vitesse_kmh} · d={a.distance_m}m · cap={a.cap_relatif_deg}°
            {a.ecart_lateral_m !== 0 && ` · e=${a.ecart_lateral_m}m`}
            {a.acceleration_ms2 !== 0 && ` · a=${a.acceleration_ms2 > 0 ? "+" : ""}${a.acceleration_ms2}m/s²`}
          </span>
          <button className="del" onClick={() => rmAgent(i)}>✕</button>
        </div>
      ))}

      <div style={{ padding: 10, background: "var(--panel-alt)", borderRadius: 6, marginTop: 8 }}>
        <div className="row-2">
          <div className="field">
            <label>Type</label>
            <select value={ag.type_agent} onChange={(e) => setAg({ ...ag, type_agent: e.target.value })}>
              {enums.type_agent.map((v) => <option key={v}>{v}</option>)}
            </select>
          </div>
          <div className="field">
            <label>V (km/h)</label>
            <input type="number" value={ag.vitesse_kmh}
              onChange={(e) => setAg({ ...ag, vitesse_kmh: num(e.target.value) })} />
          </div>
        </div>
        <div className="row-3">
          <div className="field">
            <label>Dist (m)</label>
            <input type="number" value={ag.distance_m}
              onChange={(e) => setAg({ ...ag, distance_m: num(e.target.value) })} />
          </div>
          <div className="field">
            <label>Cap (°)</label>
            <input type="number" value={ag.cap_relatif_deg}
              onChange={(e) => setAg({ ...ag, cap_relatif_deg: num(e.target.value) })} />
          </div>
          <div className="field">
            <label>Écart (m)</label>
            <input type="number" value={ag.ecart_lateral_m}
              onChange={(e) => setAg({ ...ag, ecart_lateral_m: num(e.target.value) })} />
          </div>
        </div>
        <div className="row-2">
          <div className="field">
            <label>Accél. (m/s²)</label>
            <input type="number" step="0.5" value={ag.acceleration_ms2}
              onChange={(e) => setAg({ ...ag, acceleration_ms2: num(e.target.value) })} />
          </div>
          <div className="field" style={{ justifyContent: "flex-end" }}>
            <label className="checkbox" style={{ marginTop: 20 }}>
              <input type="checkbox" checked={ag.profondeur_mesuree}
                onChange={(e) => setAg({ ...ag, profondeur_mesuree: e.target.checked })} />
              Profondeur mesurée
            </label>
          </div>
        </div>
        <button className="btn" style={{ width: "100%" }} onClick={addAgent}>+ Ajouter cet agent</button>
      </div>

      {onResetLayout && (
        <div style={{ marginTop: 16, textAlign: "center" }}>
          <button
            className="btn"
            style={{ fontSize: 11, padding: "4px 10px", color: "var(--text-mute)" }}
            onClick={onResetLayout}
            title="Rétablir les largeurs par défaut des panneaux"
          >
            ⟲ Réinitialiser layout
          </button>
        </div>
      )}
    </div>
  );
}
