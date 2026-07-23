export type RiskLevel = "SAFE" | "WATCH" | "DANGER" | "CRITICAL";

export interface AgentIn {
  type_agent: string;
  vitesse_kmh: number;
  distance_m: number;
  cap_relatif_deg: number;
  acceleration_ms2: number;
  ecart_lateral_m: number;
  profondeur_mesuree: boolean;
}

export interface ScenarioIn {
  vitesse_ego_kmh: number;
  type_route: string;
  geometrie: string;
  limite_vitesse_kmh: number;
  zone_travaux: boolean;
  etat_route: string;
  meteo: string;
  heure: string;
  visibilite_m: number;
  agents: AgentIn[];
}

export interface AgentResult {
  type: string;
  distance: number;
  ttc: number | null;
  thw: number | null;
  pet: number | null;
  rss: number;
  ratio_rss: number | null;
  ci: number;
  drac: number;
  niveau: RiskLevel;
  niveaux_par_metrique: Record<string, RiskLevel>;
  metrique_decisive: string;
  metrique_impact: string;
  corroboration: number;
  contributions: Record<string, number>;
}

export interface EvaluateResult {
  niveau_global: RiskLevel;
  avertissements: string[];
  agents: AgentResult[];
}

export interface Frame {
  t: number;
  niveau: RiskLevel;
  collision: boolean;
  ego: { x: number; y: number; vitesse_kmh: number; freinage: boolean };
  agents: {
    x: number;
    y: number;
    niveau: RiskLevel;
    ttc: number | null;
    thw: number | null;
    distance: number;
    rss: number;
    drac: number;
  }[];
}

export interface SimulateResult {
  diagnostic: string;
  collision: boolean;
  duree_s: number;
  n_agents: number;
  types_agents: string[];
  mu_g: number;
  geometrie: string;
  frames: Frame[];
}

export interface Preset {
  id: string;
  nom: string;
  famille: string;
  niveau_attendu: RiskLevel;
}

export interface Enums {
  type_route: string[];
  geometrie: string[];
  etat_route: string[];
  meteo: string[];
  heure: string[];
  type_agent: string[];
}

export const NIVEAUX: RiskLevel[] = ["SAFE", "WATCH", "DANGER", "CRITICAL"];

export const COULEURS_NIVEAU: Record<RiskLevel, { bg: string; fg: string; strong: string }> = {
  SAFE: { bg: "#e6f4ea", fg: "#1b5e20", strong: "#2e7d32" },
  WATCH: { bg: "#fff8e1", fg: "#6d5200", strong: "#f9a825" },
  DANGER: { bg: "#ffe0b2", fg: "#7a3d00", strong: "#ef6c00" },
  CRITICAL: { bg: "#ffcdd2", fg: "#8a1c1c", strong: "#c62828" },
};

export interface Contraintes {
  meteo_routes: Record<string, string[]>;
  vis_meteo: Record<string, [number, number]>;
  facteur_nuit: number;
  limites_route: Record<string, number[]>;
  zone_travaux_limites: number[];
  marge_vitesse_ego: number;
}
