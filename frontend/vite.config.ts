import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'fs';
import path from 'path';
import { defineConfig, loadEnv, type ProxyOptions } from 'vite';

// Port du front en dev et en `vite preview` -- 3000 conservé depuis l'ère
// Express : c'est l'origine déjà autorisée par `CORS_ORIGINS` côté backend
// et citée dans toute la documentation. `strictPort` : si 3000 est pris, on
// échoue franchement plutôt que de basculer en silence sur un autre port
// (que le backend ne connaîtrait pas).
const DEV_PORT = 3000;

// Défaut cohérent avec `uv run uvicorn app.main:app --reload --port 8000`
// (backend/README.md).
const DEFAULT_BACKEND_URL = 'http://localhost:8000';

/**
 * Valide `BACKEND_URL` dès le démarrage : une faute de frappe doit faire
 * échouer `npm run dev` avec un message clair, jamais produire un proxy qui
 * renvoie des 502 incompréhensibles au premier appel d'API.
 */
function resolveBackendUrl(raw: string | undefined): string {
  const value = (raw ?? '').trim() || DEFAULT_BACKEND_URL;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`BACKEND_URL invalide (URL absolue attendue, ex. ${DEFAULT_BACKEND_URL}) : "${value}"`);
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(`BACKEND_URL doit utiliser http:// ou https:// : "${value}"`);
  }
  // Origine seule : le chemin /api/v1 est conservé tel quel par le proxy.
  return parsed.origin;
}

interface VercelHeaderRule {
  source: string;
  headers: { key: string; value: string }[];
}

/**
 * En-têtes de sécurité de production, relus depuis vercel.json (seule source
 * de vérité) pour que `npm run preview` serve le build EXACTEMENT avec les
 * mêmes en-têtes (CSP comprise) que la production : une CSP trop stricte se
 * voit alors en local, pas après le déploiement.
 */
function productionSecurityHeaders(): Record<string, string> {
  const config = JSON.parse(readFileSync(path.resolve(__dirname, 'vercel.json'), 'utf-8')) as {
    headers?: VercelHeaderRule[];
  };
  const globalRule = config.headers?.find((rule) => rule.source === '/(.*)');
  return Object.fromEntries((globalRule?.headers ?? []).map(({ key, value }) => [key, value]));
}

export default defineConfig(({ mode }) => {
  // Préfixe '' : lit aussi les variables NON préfixées `VITE_` (BACKEND_URL)
  // depuis .env / .env.local -- uniquement ici, côté Node. Elles ne sont
  // jamais injectées dans le bundle navigateur (seules les `VITE_*` le sont).
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env };
  const backendUrl = resolveBackendUrl(env.BACKEND_URL);

  // Proxy de DEV uniquement (et `vite preview` pour tester le build en
  // local) : le front parle toujours en relatif à /api/v1 (src/lib/api/http.ts),
  // c'est ce proxy qui route vers FastAPI. En production, aucun serveur Node
  // ne tourne côté front -- voir frontend/README.md, « Production ».
  const apiProxy: Record<string, ProxyOptions> = {
    '/api/v1': {
      target: backendUrl,
      // Réécrit l'en-tête Host vers celui du backend (comportement de
      // l'ancien proxy Express, `changeOrigin: true`).
      changeOrigin: true,
    },
  };

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      port: DEV_PORT,
      strictPort: true,
      proxy: apiProxy,
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
    },
    preview: {
      port: DEV_PORT,
      strictPort: true,
      proxy: apiProxy,
      headers: productionSecurityHeaders(),
    },
  };
});
