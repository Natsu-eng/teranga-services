/// <reference types="vite/client" />

// Variables d'environnement exposées au navigateur (préfixe `VITE_`, figées
// au build). Toute autre variable reste côté Node (vite.config.ts) et n'est
// jamais injectée dans le bundle -- n'y mettre AUCUN secret.
interface ImportMetaEnv {
  /** Base absolue de l'API en production multi-origines, ex. `https://api.teranga.sn/api/v1`. Défaut : `/api/v1` (même origine). Voir src/lib/api/base-url.ts. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
