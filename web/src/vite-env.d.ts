// Types d'environnement Vite — déclarations autosuffisantes (aucune dépendance
// à la résolution de `vite/client`, pour un build robuste sur tout CI).

interface ImportMetaEnv {
  readonly PROD: boolean;
  readonly DEV: boolean;
  readonly MODE: string;
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.css";
