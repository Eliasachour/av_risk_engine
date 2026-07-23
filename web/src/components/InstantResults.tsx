import type { EvaluateResult, RiskLevel } from "../types";
import { COULEURS_NIVEAU } from "../types";

interface Props {
  result: EvaluateResult | null;
  loading: boolean;
}

const METRIQUES = ["TTC", "THW", "PET", "RSS", "CI", "DRAC"] as const;

const SEUILS: Record<string, { texte: string; bandes: { label: string; range: string; color: RiskLevel }[] }> = {
  TTC: {
    texte: "Temps avant collision — plus haut = plus sûr",
    bandes: [
      { label: "SAFE", range: "> 4 s", color: "SAFE" },
      { label: "WATCH", range: "2–4 s", color: "WATCH" },
      { label: "DANGER", range: "1–2 s", color: "DANGER" },
      { label: "CRITICAL", range: "< 1 s", color: "CRITICAL" },
    ],
  },
  THW: {
    texte: "Time headway — marge de suivi longitudinal",
    bandes: [
      { label: "SAFE", range: "> 2 s", color: "SAFE" },
      { label: "WATCH", range: "1–2 s", color: "WATCH" },
      { label: "DANGER", range: "0.5–1 s", color: "DANGER" },
      { label: "CRITICAL", range: "< 0.5 s", color: "CRITICAL" },
    ],
  },
  PET: {
    texte: "Post-Encroachment Time — délai à un croisement",
    bandes: [
      { label: "SAFE", range: "> 3 s", color: "SAFE" },
      { label: "WATCH", range: "1.5–3 s", color: "WATCH" },
      { label: "DANGER", range: "0.5–1.5 s", color: "DANGER" },
      { label: "CRITICAL", range: "< 0.5 s", color: "CRITICAL" },
    ],
  },
  RSS: {
    texte: "Distance de sécurité prouvée (Shalev-Shwartz) — binaire",
    bandes: [
      { label: "SAFE", range: "d ≥ d_rss", color: "SAFE" },
      { label: "DANGER", range: "d < d_rss (violé)", color: "DANGER" },
    ],
  },
  CI: {
    texte: "Criticality Index — composite (imminence × sévérité)",
    bandes: [
      { label: "SAFE", range: "< 0.3", color: "SAFE" },
      { label: "WATCH", range: "0.3–0.6", color: "WATCH" },
      { label: "DANGER", range: "0.6–0.85", color: "DANGER" },
      { label: "CRITICAL", range: "> 0.85", color: "CRITICAL" },
    ],
  },
  DRAC: {
    texte: "Décélération requise (m/s²) — plafond ≈ µ·g",
    bandes: [
      { label: "SAFE", range: "< 3", color: "SAFE" },
      { label: "WATCH", range: "3–6", color: "WATCH" },
      { label: "DANGER", range: "6–8", color: "DANGER" },
      { label: "CRITICAL", range: "> 8", color: "CRITICAL" },
    ],
  },
};

function formatValue(name: string, agent: any): string {
  const map: Record<string, string> = {
    TTC: agent.ttc === null ? "∞" : agent.ttc.toFixed(2) + "s",
    THW: agent.thw === null ? "∞" : agent.thw.toFixed(2) + "s",
    PET: agent.pet === null ? "∞" : agent.pet.toFixed(2) + "s",
    RSS: agent.ratio_rss !== null && agent.ratio_rss < 1 ? "violé" : "OK",
    CI: agent.ci.toFixed(2),
    DRAC: agent.drac.toFixed(1),
  };
  return map[name] || "?";
}

function jaugePercent(name: string, agent: any): number {
  const v = { TTC: agent.ttc, THW: agent.thw, PET: agent.pet, CI: agent.ci, DRAC: agent.drac }[name];
  if (v === null || v === undefined) return 0;
  if (name === "TTC") return Math.max(0, Math.min(100, 100 - (v / 4) * 100));
  if (name === "THW") return Math.max(0, Math.min(100, 100 - (v / 2) * 100));
  if (name === "PET") return Math.max(0, Math.min(100, 100 - (v / 3) * 100));
  if (name === "CI") return Math.max(0, Math.min(100, v * 100));
  if (name === "DRAC") return Math.max(0, Math.min(100, (v / 9) * 100));
  return 0;
}

function TooltipSeuils({ nom }: { nom: string }) {
  const s = SEUILS[nom];
  if (!s) return null;
  return (
    <div className="tooltip-seuils">
      <div className="tt-titre">{s.texte}</div>
      {s.bandes.map((b) => {
        const c = COULEURS_NIVEAU[b.color];
        return (
          <div key={b.label} className="tt-bande">
            <span className="tt-badge" style={{ background: c.bg, color: c.fg }}>{b.label}</span>
            <span className="tt-range mono">{b.range}</span>
          </div>
        );
      })}
    </div>
  );
}

export function InstantResults({ result, loading }: Props) {
  if (loading && !result) {
    return <div className="panel"><h2>Évaluation instantanée</h2><p style={{ color: "var(--text-mute)" }}>Calcul...</p></div>;
  }
  if (!result) {
    return (
      <div className="panel">
        <h2>Évaluation à t = 0</h2>
        <div className="empty-state">
          <span className="icon">◮</span>
          <span>Aucun agent dans la scène</span>
          <span className="hint">Ajoutez un usager (ou chargez un préréglage SC-01…24) pour évaluer le risque en direct.</span>
        </div>
      </div>
    );
  }

  const nivColor = COULEURS_NIVEAU[result.niveau_global];

  return (
    <div className="panel">
      <h2>Évaluation à t = 0</h2>

      <div className={`niveau-hero ${result.niveau_global}`}
        style={{ background: nivColor.bg, color: nivColor.fg }}>
        <div className="label">Niveau global</div>
        <div className="value">{result.niveau_global}</div>
      </div>

      {result.avertissements.length > 0 && (
        <div className="info-diag warn">
          <strong>Entrées assainies :</strong> {result.avertissements.join(" · ")}
        </div>
      )}

      {result.agents.map((ag, i) => (
        <div key={i} style={{ marginBottom: 16 }}>
          <h3 style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>{ag.type} #{i + 1} — {ag.distance.toFixed(0)}m</span>
            <span style={{
              fontSize: 10, padding: "2px 6px", borderRadius: 4,
              background: COULEURS_NIVEAU[ag.niveau].bg,
              color: COULEURS_NIVEAU[ag.niveau].fg,
            }}>
              {ag.niveau}
            </span>
          </h3>

          {ag.metrique_decisive !== "—" && (
            <div style={{
              fontSize: 11, color: "var(--text-mute)", marginBottom: 8,
              padding: "6px 10px", background: "var(--panel-alt)", borderRadius: 6,
              borderLeft: "3px solid " + COULEURS_NIVEAU[ag.niveau].strong,
            }}>
              Déclencheur : <strong style={{ color: "var(--text)" }}>{ag.metrique_decisive}</strong>
              {" · "}Impact principal : <strong style={{ color: "var(--text)" }}>{ag.metrique_impact}</strong>
            </div>
          )}

          <div className="grid-metriques">
            {METRIQUES.map((m) => {
              const niv = ag.niveaux_par_metrique[m] as RiskLevel;
              const c = COULEURS_NIVEAU[niv];
              return (
                <div key={m} className="card-metrique tooltip-host" style={{ borderLeftColor: c.strong }}>
                  <div className="nom">{m}</div>
                  <div className="val mono" style={{ color: c.fg }}>{formatValue(m, ag)}</div>
                  <span className="badge" style={{ background: c.bg, color: c.fg }}>{niv}</span>
                  {m !== "RSS" && (
                    <div className="jauge">
                      <div style={{ width: `${jaugePercent(m, ag)}%`, background: c.strong }} />
                    </div>
                  )}
                  <TooltipSeuils nom={m} />
                </div>
              );
            })}
          </div>

          <h3>Impact des métriques (corroboration : {ag.corroboration})</h3>
          <div>
            {Object.entries(ag.contributions)
              .sort(([, a], [, b]) => b - a)
              .filter(([, v]) => v > 0)
              .slice(0, 5)
              .map(([nom, v]) => (
                <div key={nom} className="impact-item">
                  <span className="nom">{nom}</span>
                  <div className="barre"><div style={{ width: `${v * 100}%` }} /></div>
                  <span className="val mono">{v.toFixed(2)}</span>
                </div>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}
