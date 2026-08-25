import { useEffect, useRef, useState } from "react";
import { ScenarioForm } from "./components/ScenarioForm";
import { InstantResults } from "./components/InstantResults";
import { Simulation } from "./components/Simulation";
import { api, isAbort } from "./api";
import type { ScenarioIn, Enums, EvaluateResult, SimulateResult } from "./types";

const DEFAULT_SCENARIO: ScenarioIn = {
  vitesse_ego_kmh: 80,
  type_route: "nationale",
  geometrie: "droite",
  limite_vitesse_kmh: 90,
  zone_travaux: false,
  etat_route: "sec",
  meteo: "clair",
  heure: "jour",
  visibilite_m: 500,
  agents: [],
};

// Largeurs par défaut : 340px pour le formulaire, moitié-moitié pour le reste
const LAYOUT_STORAGE = "avrisk_layout_v1";

function loadLayout(): { col1: number; col2Frac: number } {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE);
    if (raw) return JSON.parse(raw);
  } catch {}
  return { col1: 340, col2Frac: 0.5 };
}

export default function App() {
  const [scenario, setScenario] = useState<ScenarioIn>(DEFAULT_SCENARIO);
  const [enums, setEnums] = useState<Enums | null>(null);
  const [evalResult, setEvalResult] = useState<EvaluateResult | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [sim, setSim] = useState<SimulateResult | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const debounceRef = useRef<number | null>(null);

  // Layout ajustable
  const [layout, setLayout] = useState(loadLayout);
  const dragRef = useRef<"col1" | "col2" | null>(null);
  const appRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.enums()
      .then((e) => { setEnums(e); setApiOk(true); })
      .catch(() => setApiOk(false));
  }, []);

  useEffect(() => {
    if (scenario.agents.length === 0) { setEvalResult(null); setErreur(null); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(async () => {
      setEvalLoading(true);
      try {
        setEvalResult(await api.evaluate(scenario));
        setErreur(null);
        setApiOk(true);
      } catch (e: any) {
        if (!isAbort(e)) {
          setErreur(e?.message ?? "Erreur inconnue");
          if (e?.status === undefined) setApiOk(false); // réseau coupé
        }
      } finally {
        setEvalLoading(false);
      }
    }, 300);
  }, [scenario]);

  // Persistance du layout
  useEffect(() => {
    localStorage.setItem(LAYOUT_STORAGE, JSON.stringify(layout));
  }, [layout]);

  // Gestion du drag des splitters
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragRef.current || !appRef.current) return;
      const rect = appRef.current.getBoundingClientRect();
      const total = rect.width - 24;                          // - padding
      const splitterW = 12;                                    // 2 x 6px
      if (dragRef.current === "col1") {
        const newCol1 = Math.max(240, Math.min(600, e.clientX - rect.left - 12));
        setLayout((L) => ({ ...L, col1: newCol1 }));
      } else {
        const restW = total - layout.col1 - splitterW;
        const posInRest = e.clientX - rect.left - 12 - layout.col1 - 6;
        const frac = Math.max(0.2, Math.min(0.8, posInRest / restW));
        setLayout((L) => ({ ...L, col2Frac: frac }));
      }
    };
    const onUp = () => {
      dragRef.current = null;
      document.body.style.cursor = "";
      document.querySelectorAll(".splitter.dragging").forEach((el) =>
        el.classList.remove("dragging"));
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [layout.col1]);

  const startDrag = (which: "col1" | "col2") => (e: React.MouseEvent) => {
    dragRef.current = which;
    document.body.style.cursor = "col-resize";
    (e.currentTarget as HTMLElement).classList.add("dragging");
  };

  const resetLayout = () => setLayout({ col1: 340, col2Frac: 0.5 });

  const runSim = async (reaction: boolean) => {
    if (scenario.agents.length === 0) return;
    setSimLoading(true);
    try {
      setSim(await api.simulate(scenario, reaction));
      setErreur(null);
      setApiOk(true);
    } catch (e: any) {
      if (!isAbort(e)) {
        setErreur(e?.message ?? "Erreur inconnue");
        if (e?.status === undefined) setApiOk(false);
      }
    } finally {
      setSimLoading(false);
    }
  };

  if (!enums) {
    return (
      <div className="boot">
        <div className="boot-card">
          <div className="boot-title">AV Risk Engine</div>
          {apiOk === false ? (
            <>
              <p>Impossible de joindre l'API (port 8000).</p>
              <p className="boot-hint mono">python3 api.py</p>
              <button className="btn btn-primary" onClick={() => location.reload()}>Réessayer</button>
            </>
          ) : (
            <p>Connexion à l'API…</p>
          )}
        </div>
      </div>
    );
  }

  // CSS variables pour piloter la grille
  const style = {
    "--col-1": `${layout.col1}px`,
    "--col-2": `${layout.col2Frac}fr`,
    "--col-3": `${1 - layout.col2Frac}fr`,
  } as React.CSSProperties;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-logo">◮</span>
          <span className="brand-name">AV Risk Engine</span>
          <span className="brand-sub">moteur d'évaluation du risque · démonstrateur</span>
        </div>
        <div className="topbar-right">
          {erreur && <span className="err-chip" title={erreur}>⚠ {erreur}</span>}
          <span className={`status-dot ${apiOk === false ? "off" : "on"}`} />
          <span className="status-label">{apiOk === false ? "API hors ligne" : "API en ligne"}</span>
        </div>
      </header>
      <div className="app" ref={appRef} style={style}>
        <ScenarioForm
          scenario={scenario}
          onChange={setScenario}
          onSimulate={runSim}
          enums={enums}
          onResetLayout={resetLayout}
        />
        <div className="splitter" onMouseDown={startDrag("col1")} title="Glisser pour redimensionner" />
        <InstantResults result={evalResult} loading={evalLoading} />
        <div className="splitter" onMouseDown={startDrag("col2")} title="Glisser pour redimensionner" />
        <Simulation sim={sim} loading={simLoading} />
      </div>
    </div>
  );
}
