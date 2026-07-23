import type { ScenarioIn, EvaluateResult, SimulateResult, Preset, Enums } from "./types";

const BASE = "/api";

/** Erreur API avec message lisible (extrait du champ `detail` de FastAPI). */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Un AbortController par "canal" : une nouvelle requête evaluate annule la
// précédente encore en vol (évite les réponses dans le désordre et la
// saturation du backend quand on tape vite dans le formulaire).
const controllers: Record<string, AbortController> = {};

async function req<T>(path: string, opts?: RequestInit, canal?: string): Promise<T> {
  let signal: AbortSignal | undefined;
  if (canal) {
    controllers[canal]?.abort();
    controllers[canal] = new AbortController();
    signal = controllers[canal].signal;
  }
  const timeout = setTimeout(() => canal && controllers[canal]?.abort(), 15000);
  try {
    const r = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal,
      ...opts,
    });
    if (!r.ok) {
      let msg = `Erreur ${r.status}`;
      try {
        const body = await r.json();
        if (body?.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch { /* corps non-JSON */ }
      throw new ApiError(r.status, msg);
    }
    return r.json();
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  enums: () => req<Enums>("/enums"),
  presets: () => req<Preset[]>("/presets"),
  preset: (id: string) =>
    req<{ id: string; nom: string; niveau_attendu: string; scenario: ScenarioIn }>(`/presets/${id}`),
  seuils: () => req<Record<string, any>>("/seuils"),
  evaluate: (s: ScenarioIn) =>
    req<EvaluateResult>("/evaluate", { method: "POST", body: JSON.stringify(s) }, "evaluate"),
  simulate: (s: ScenarioIn, reaction: boolean) =>
    req<SimulateResult>("/simulate", { method: "POST", body: JSON.stringify({ scenario: s, reaction }) }, "simulate"),
};

/** Vrai si l'erreur est une annulation volontaire (à ignorer silencieusement). */
export const isAbort = (e: unknown) =>
  e instanceof DOMException && e.name === "AbortError";
