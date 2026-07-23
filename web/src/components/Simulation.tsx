import { useEffect, useMemo, useRef, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ReferenceArea, Legend, Area, ComposedChart,
} from "recharts";
import type { SimulateResult, RiskLevel } from "../types";
import { COULEURS_NIVEAU } from "../types";

interface Props {
  sim: SimulateResult | null;
  loading: boolean;
}

type Onglet = "topdown" | "courbes";

const PALETTE = ["#2563eb", "#7c3aed", "#0891b2", "#dc2626", "#059669", "#d97706"];
const NIVEAU_TO_INT: Record<RiskLevel, number> = { SAFE: 0, WATCH: 1, DANGER: 2, CRITICAL: 3 };

export function Simulation({ sim, loading }: Props) {
  const [onglet, setOnglet] = useState<Onglet>("topdown");
  const [tIdx, setTIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [repereAbsolu, setRepereAbsolu] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    setTIdx(0);
    setPlaying(false);
  }, [sim]);

  useEffect(() => {
    if (playing && sim) {
      timerRef.current = window.setInterval(() => {
        setTIdx((i) => {
          if (!sim.frames || i >= sim.frames.length - 1) {
            setPlaying(false);
            return i;
          }
          return i + 1;
        });
      }, 80);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [playing, sim]);

  // Données pré-calculées pour les courbes
  const donnees = useMemo(() => {
    if (!sim) return [];
    return sim.frames.map((f) => {
      const row: any = {
        t: f.t,
        ego_kmh: f.ego.vitesse_kmh,
        niveau_int: NIVEAU_TO_INT[f.niveau],
      };
      f.agents.forEach((a, i) => {
        row[`dist_${i}`] = a.distance;
        row[`rss_${i}`] = a.rss;
        row[`ttc_${i}`] = a.ttc !== null && a.ttc < 10 ? a.ttc : null;
        row[`thw_${i}`] = a.thw !== null && a.thw < 10 ? a.thw : null;
        row[`drac_${i}`] = a.drac;
      });
      return row;
    });
  }, [sim]);

  if (loading && !sim) {
    return <div className="panel"><h2>Simulation</h2><p style={{ color: "var(--text-mute)" }}>Simulation en cours...</p></div>;
  }
  if (!sim) {
    return (
      <div className="panel">
        <h2>Simulation</h2>
        <div className="empty-state">
          <span className="icon">▶</span>
          <span>Aucune simulation lancée</span>
          <span className="hint">Configurez le scénario puis cliquez « Simuler » — vous obtiendrez la vue de dessus animée et les courbes.</span>
        </div>
      </div>
    );
  }

  const frame = sim.frames[tIdx];
  const isCol = sim.collision;

  return (
    <div className="panel">
      <h2>Simulation ({sim.frames.length} pas · {sim.duree_s.toFixed(1)}s)</h2>

      <div className={`info-diag ${isCol ? "warn" : ""}`}>
        <strong>{isCol ? "Collision" : "Pas de collision"} :</strong> {sim.diagnostic}
      </div>

      <div className="tabs">
        <div className={`tab ${onglet === "topdown" ? "active" : ""}`} onClick={() => setOnglet("topdown")}>
          Vue de dessus
        </div>
        <div className={`tab ${onglet === "courbes" ? "active" : ""}`} onClick={() => setOnglet("courbes")}>
          Courbes ({sim.n_agents} agent{sim.n_agents > 1 ? "s" : ""})
        </div>
      </div>

      {onglet === "topdown" && (
        <TopDown
          frame={frame}
          sim={sim}
          repereAbsolu={repereAbsolu}
          setRepereAbsolu={setRepereAbsolu}
          tIdx={tIdx}
        />
      )}
      {onglet === "courbes" && (
        <Courbes donnees={donnees} sim={sim} tCurrent={frame?.t ?? 0} />
      )}

      <div className="timeline">
        <button className="btn btn-play btn-primary" onClick={() => setPlaying(!playing)}>
          {playing ? "⏸" : "▶"}
        </button>
        <input
          type="range"
          min={0}
          max={sim.frames.length - 1}
          value={tIdx}
          onChange={(e) => { setTIdx(+e.target.value); setPlaying(false); }}
        />
        <span className="t-label">t = {frame?.t.toFixed(1) ?? "0.0"}s</span>
      </div>
    </div>
  );
}

/* -------------------- Vue de dessus (SVG animée, enrichie) -------------------- */

function TopDown({
  frame, sim, repereAbsolu, setRepereAbsolu, tIdx,
}: {
  frame: any; sim: SimulateResult; repereAbsolu: boolean;
  setRepereAbsolu: (v: boolean) => void; tIdx: number;
}) {
  // Transformation selon le repère (ego ou monde)
  const pos = (px: number, py: number, egoX: number, egoY: number) =>
    repereAbsolu ? [px, py] : [px - egoX, py - egoY];

  // Bounding box englobante sur toute la séquence
  const bbox = useMemo(() => {
    const xs: number[] = [], ys: number[] = [];
    sim.frames.forEach((f) => {
      const [ex, ey] = pos(f.ego.x, f.ego.y, f.ego.x, f.ego.y);
      xs.push(ex); ys.push(ey);
      f.agents.forEach((a) => {
        const [x, y] = pos(a.x, a.y, f.ego.x, f.ego.y);
        xs.push(x); ys.push(y);
      });
    });
    const pad = 8;
    return {
      xMin: Math.min(...xs) - pad,
      xMax: Math.max(...xs) + pad,
      yMin: Math.min(-4, ...ys) - pad,
      yMax: Math.max(4, ...ys) + pad,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sim, repereAbsolu]);

  const W = 600, H = 280;
  const scaleX = (x: number) => ((x - bbox.xMin) / (bbox.xMax - bbox.xMin)) * W;
  const scaleY = (y: number) => H - ((y - bbox.yMin) / (bbox.yMax - bbox.yMin)) * H;

  // Graduations en mètres (5 traits par axe)
  const xTicks = 5, yTicks = 3;
  const xStep = (bbox.xMax - bbox.xMin) / xTicks;
  const yStep = (bbox.yMax - bbox.yMin) / yTicks;

  const MARKERS: Record<string, string> = {
    voiture: "▪", camion: "▪", pieton: "●", cycliste: "◆", ouvrier: "✕",
  };

  // Trace fantôme (position passée) des agents
  const traceAgents = sim.frames.slice(0, tIdx + 1);
  const [egoX, egoY] = [frame.ego.x, frame.ego.y];

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 8, fontSize: 12 }}>
        <button
          className={`btn ${!repereAbsolu ? "btn-primary" : ""}`}
          style={{ padding: "4px 10px", fontSize: 11 }}
          onClick={() => setRepereAbsolu(false)}
        >
          Repère ego
        </button>
        <button
          className={`btn ${repereAbsolu ? "btn-primary" : ""}`}
          style={{ padding: "4px 10px", fontSize: 11 }}
          onClick={() => setRepereAbsolu(true)}
        >
          Repère monde
        </button>
      </div>

      <div className="topdown">
        <svg viewBox={`0 0 ${W} ${H}`}>          {/* Graduations subtiles */}
          {Array.from({ length: xTicks + 1 }, (_, i) => bbox.xMin + i * xStep).map((x, i) => (
            <g key={`gx-${i}`}>
              <line x1={scaleX(x)} x2={scaleX(x)} y1={H - 4} y2={H} stroke="#c8ced9" />
              <text x={scaleX(x)} y={H - 6} textAnchor="middle" fontSize={9} fill="#8a94a6">
                {x.toFixed(0)}
              </text>
            </g>
          ))}
          {Array.from({ length: yTicks + 1 }, (_, i) => bbox.yMin + i * yStep).map((y, i) => (
            <g key={`gy-${i}`}>
              <line x1={0} x2={4} y1={scaleY(y)} y2={scaleY(y)} stroke="#c8ced9" />
              <text x={6} y={scaleY(y) + 3} fontSize={9} fill="#8a94a6">{y.toFixed(0)}</text>
            </g>
          ))}

          {/* Voies : droites en repère ego droit, sinusoïdales en virage */}
          {!repereAbsolu && (
            (() => {
              const enVirage = sim.geometrie === "virage";
              if (!enVirage) {
                return (
                  <>
                    <line x1={0} x2={W} y1={scaleY(1.75)} y2={scaleY(1.75)}
                      stroke="#c8ced9" strokeDasharray="4 4" />
                    <line x1={0} x2={W} y1={scaleY(-1.75)} y2={scaleY(-1.75)}
                      stroke="#c8ced9" strokeDasharray="4 4" />
                  </>
                );
              }
              // Route courbée : deux polylignes sinusoïdales douces + fond léger
              const N = 60;
              const amp = 2.5;                     // amplitude latérale du virage
              const periode = bbox.xMax - bbox.xMin;
              const buildPath = (offset: number) => {
                const pts: string[] = [];
                for (let i = 0; i <= N; i++) {
                  const x = bbox.xMin + (i / N) * periode;
                  const y = amp * Math.sin(((x - bbox.xMin) / periode) * Math.PI) + offset;
                  pts.push(`${scaleX(x)},${scaleY(y)}`);
                }
                return pts.join(" ");
              };
              const bordGauche = buildPath(1.75);
              const bordDroit = buildPath(-1.75);
              const axe = buildPath(0);
              return (
                <>
                  {/* Remplissage clair de la chaussée */}
                  <polygon
                    points={`${bordGauche} ${buildPath(-1.75).split(" ").reverse().join(" ")}`}
                    fill="#eef1f6" opacity={0.55}
                  />
                  <polyline points={bordGauche} fill="none"
                    stroke="#c8ced9" strokeDasharray="4 4" strokeWidth={1.2} />
                  <polyline points={bordDroit} fill="none"
                    stroke="#c8ced9" strokeDasharray="4 4" strokeWidth={1.2} />
                  <polyline points={axe} fill="none"
                    stroke="#dbdfe6" strokeDasharray="2 6" strokeWidth={0.8} />
                </>
              );
            })()
          )}

          {/* Badge VIRAGE en coin */}
          {sim.geometrie === "virage" && !repereAbsolu && (
            <g>
              <rect x={W - 88} y={40} width={80} height={20} rx={4}
                fill="#fef3c7" stroke="#f59e0b" strokeWidth={0.6} />
              <text x={W - 48} y={54} textAnchor="middle" fontSize={10}
                fontWeight="bold" fill="#92400e" letterSpacing="0.05em">
                VIRAGE
              </text>
            </g>
          )}

          {/* Trace ego (fantôme) */}
          <polyline
            fill="none" stroke="#2563eb" strokeWidth={1.5} strokeDasharray="3 3" opacity={0.35}
            points={traceAgents.map((f) => {
              const [x, y] = pos(f.ego.x, f.ego.y, egoX, egoY);
              return `${scaleX(x)},${scaleY(y)}`;
            }).join(" ")}
          />

          {/* Traces agents (fantômes) */}
          {frame.agents.map((_: any, i: number) => {
            const points = traceAgents.map((f) => {
              const a = f.agents[i];
              if (!a) return "";
              const [x, y] = pos(a.x, a.y, egoX, egoY);
              return `${scaleX(x)},${scaleY(y)}`;
            }).filter(Boolean).join(" ");
            return (
              <polyline
                key={`tr-${i}`}
                fill="none"
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={1.3}
                strokeDasharray="2 3"
                opacity={0.4}
                points={points}
              />
            );
          })}

          {/* Halo de freinage (ego) */}
          {frame.ego.freinage && (() => {
            const [x, y] = pos(frame.ego.x, frame.ego.y, egoX, egoY);
            return (
              <circle cx={scaleX(x)} cy={scaleY(y)} r={22}
                fill="#c62828" opacity={0.15}>
                <animate attributeName="r" from="16" to="26" dur="1.2s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="0.28" to="0" dur="1.2s" repeatCount="indefinite" />
              </circle>
            );
          })()}

          {/* Ego */}
          {(() => {
            const [x, y] = pos(frame.ego.x, frame.ego.y, egoX, egoY);
            return (
              <g transform={`translate(${scaleX(x)}, ${scaleY(y)})`}>
                <polygon
                  points="-10,-8 -10,8 10,0"
                  fill={frame.ego.freinage ? "#c62828" : "#2563eb"}
                  stroke="white" strokeWidth={1}
                />
              </g>
            );
          })()}

          {/* Agents */}
          {frame.agents.map((a: any, i: number) => {
            const type = sim.types_agents[i] || "voiture";
            const c = COULEURS_NIVEAU[a.niveau as RiskLevel];
            const [x, y] = pos(a.x, a.y, egoX, egoY);
            return (
              <g key={i} transform={`translate(${scaleX(x)}, ${scaleY(y)})`}>
                <circle r={9} fill={c.strong} stroke="white" strokeWidth={1.5} />
                <text y={4} textAnchor="middle" fontSize={11} fill="white" fontWeight="bold">
                  {MARKERS[type] || "●"}
                </text>
              </g>
            );
          })}

          {/* Bandeaux d'info */}
          <g>
            <rect x={8} y={8} width={140} height={26} rx={4}
              fill={COULEURS_NIVEAU[frame.niveau as RiskLevel].bg} />
            <text x={78} y={26} textAnchor="middle" fontSize={12} fontWeight="bold"
              fill={COULEURS_NIVEAU[frame.niveau as RiskLevel].fg}>
              {frame.niveau}
            </text>
          </g>
          <text x={W - 8} y={26} textAnchor="end" fontSize={11} fill="#5a6478" fontFamily="monospace">
            ego : {frame.ego.vitesse_kmh.toFixed(0)} km/h {frame.ego.freinage ? "— FREINAGE" : ""}
          </text>
        </svg>
      </div>
      {sim.geometrie === "virage" && (
        <div style={{ fontSize: 10, color: "var(--text-mute)", marginTop: 4, textAlign: "center" }}>
          Route courbée à titre indicatif — la trajectoire de l'ego reste rectiligne
          dans le modèle 2D.
        </div>
      )}
    </div>
  );
}

/* -------------------- Courbes enrichies (3 graphes + bandeau) -------------------- */

function Courbes({ donnees, sim, tCurrent }: {
  donnees: any[]; sim: SimulateResult; tCurrent: number;
}) {
  const tickStyle = { fontSize: 10, fill: "#5a6478" };
  const gridStroke = "#eef0f4";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Graphe 1 — Distances vs RSS */}
      <GrapheBloc titre="Distance réelle vs distance de sécurité RSS" hauteur={140}>
        <LineChart data={donnees} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
          <XAxis dataKey="t" tick={tickStyle} />
          <YAxis tick={tickStyle} width={40} label={{ value: "m", angle: -90, position: "insideLeft", fontSize: 10, fill: "#8a94a6" }} />
          <Tooltip contentStyle={{ fontSize: 11, borderRadius: 6 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} iconSize={8} />
          <ReferenceLine x={tCurrent} stroke="#2563eb" strokeDasharray="3 3" />
          {sim.types_agents.map((t, i) => (
            <Line key={`d${i}`} dataKey={`dist_${i}`}
              name={`d ${t} #${i + 1}`}
              stroke={PALETTE[i % PALETTE.length]} strokeWidth={1.8} dot={false} />
          ))}
          {sim.types_agents.map((_, i) => (
            <Line key={`r${i}`} dataKey={`rss_${i}`}
              name={`RSS #${i + 1}`}
              stroke={PALETTE[i % PALETTE.length]}
              strokeDasharray="4 3" strokeWidth={1.2} dot={false} opacity={0.6} />
          ))}
        </LineChart>
      </GrapheBloc>

      {/* Graphe 2 — Métriques temporelles */}
      <GrapheBloc titre="Métriques temporelles (TTC, THW), plafonnées à 10 s" hauteur={140}>
        <LineChart data={donnees} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
          <XAxis dataKey="t" tick={tickStyle} />
          <YAxis tick={tickStyle} width={40} domain={[0, 10]}
            label={{ value: "s", angle: -90, position: "insideLeft", fontSize: 10, fill: "#8a94a6" }} />
          <Tooltip contentStyle={{ fontSize: 11, borderRadius: 6 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} iconSize={8} />
          <ReferenceLine x={tCurrent} stroke="#2563eb" strokeDasharray="3 3" />
          <ReferenceLine y={4} stroke="#2e7d32" strokeDasharray="2 4" strokeWidth={1}
            label={{ value: "SAFE", position: "right", fontSize: 9, fill: "#2e7d32" }} />
          <ReferenceLine y={2} stroke="#f9a825" strokeDasharray="2 4" strokeWidth={1}
            label={{ value: "WATCH", position: "right", fontSize: 9, fill: "#f9a825" }} />
          <ReferenceLine y={1} stroke="#c62828" strokeDasharray="2 4" strokeWidth={1}
            label={{ value: "DANGER", position: "right", fontSize: 9, fill: "#c62828" }} />
          {sim.types_agents.map((t, i) => (
            <Line key={`ttc${i}`} dataKey={`ttc_${i}`}
              name={`TTC ${t} #${i + 1}`}
              stroke={PALETTE[i % PALETTE.length]} strokeWidth={1.8} dot={false} />
          ))}
          {sim.types_agents.map((_, i) => (
            <Line key={`thw${i}`} dataKey={`thw_${i}`}
              name={`THW #${i + 1}`}
              stroke={PALETTE[i % PALETTE.length]}
              strokeDasharray="2 2" strokeWidth={1.2} dot={false} opacity={0.6} />
          ))}
        </LineChart>
      </GrapheBloc>

      {/* Graphe 3 — DRAC vs µ·g */}
      <GrapheBloc titre={`Décélération requise vs disponible (µ·g = ${sim.mu_g.toFixed(1)} m/s²)`} hauteur={130}>
        <LineChart data={donnees} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
          <XAxis dataKey="t" tick={tickStyle} />
          <YAxis tick={tickStyle} width={40}
            label={{ value: "m/s²", angle: -90, position: "insideLeft", fontSize: 10, fill: "#8a94a6" }} />
          <Tooltip contentStyle={{ fontSize: 11, borderRadius: 6 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} iconSize={8} />
          <ReferenceLine x={tCurrent} stroke="#2563eb" strokeDasharray="3 3" />
          <ReferenceLine y={sim.mu_g} stroke="#c62828" strokeWidth={1.5}
            label={{ value: `µ·g = ${sim.mu_g.toFixed(1)}`, position: "right", fontSize: 10, fill: "#c62828" }} />
          {sim.types_agents.map((t, i) => (
            <Line key={`drac${i}`} dataKey={`drac_${i}`}
              name={`DRAC ${t} #${i + 1}`}
              stroke={PALETTE[i % PALETTE.length]} strokeWidth={1.8} dot={false} />
          ))}
        </LineChart>
      </GrapheBloc>

      {/* Bandeau bas — vitesse ego + niveau global */}
      <GrapheBloc titre="Vitesse de l'ego et niveau de risque global" hauteur={110}>
        <ComposedChart data={donnees} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
          <XAxis dataKey="t" tick={tickStyle} />
          <YAxis yAxisId="left" tick={tickStyle} width={40} orientation="left"
            label={{ value: "km/h", angle: -90, position: "insideLeft", fontSize: 10, fill: "#8a94a6" }} />
          <YAxis yAxisId="right" tick={tickStyle} width={45} orientation="right"
            domain={[0, 3]} ticks={[0, 1, 2, 3]}
            tickFormatter={(v) => ["S", "W", "D", "C"][v] || ""} />
          <Tooltip contentStyle={{ fontSize: 11, borderRadius: 6 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} iconSize={8} />
          <ReferenceLine x={tCurrent} stroke="#2563eb" strokeDasharray="3 3" yAxisId="left" />
          {/* Zones colorées de risque en fond */}
          <ReferenceArea yAxisId="right" y1={0} y2={1} fill="#e6f4ea" fillOpacity={0.35} />
          <ReferenceArea yAxisId="right" y1={1} y2={2} fill="#fff8e1" fillOpacity={0.4} />
          <ReferenceArea yAxisId="right" y1={2} y2={3} fill="#ffcdd2" fillOpacity={0.4} />
          <Area yAxisId="right" dataKey="niveau_int" name="Niveau"
            stroke="#5a6478" strokeWidth={1.5}
            fill="#5a647830" type="stepAfter" />
          <Line yAxisId="left" dataKey="ego_kmh" name="Vitesse ego (km/h)"
            stroke="#2563eb" strokeWidth={2} dot={false} />
        </ComposedChart>
      </GrapheBloc>
    </div>
  );
}

function GrapheBloc({ titre, hauteur, children }: { titre: string; hauteur: number; children: any }) {
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-mute)", marginBottom: 4 }}>
        {titre}
      </div>
      <div style={{ height: hauteur }}>
        <ResponsiveContainer>{children}</ResponsiveContainer>
      </div>
    </div>
  );
}
