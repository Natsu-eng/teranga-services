import { createHash } from 'crypto';
import { readFileSync } from 'fs';
import path from 'path';
import type { Plugin } from 'vite';

/**
 * Plugin Vite (build uniquement) qui produit dist/sw.js à partir du modèle
 * pwa/sw.js : il y injecte `SW_BUILD`, c'est-à-dire
 * - `shell` : index.html et les fichiers /assets/ qu'il charge (coquille
 *   précachée, pour un démarrage hors connexion) ;
 * - `version` : empreinte du build (noms des fichiers + index.html). Elle
 *   change dès qu'un fichier change, et seulement dans ce cas : un build
 *   identique ne déclenche pas de mise à jour inutile chez les utilisateurs.
 */

export interface ServiceWorkerBuild {
  version: string;
  shell: string[];
}

const TEMPLATE_PATH = path.resolve(__dirname, 'sw.js');
export const SERVICE_WORKER_FILE = 'sw.js';

/** Fichiers /assets/ référencés par index.html (script et feuilles d'entrée). */
export function shellAssetsFromHtml(html: string): string[] {
  const urls = new Set<string>();
  for (const match of html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)) {
    urls.add(match[1]);
  }
  return [...urls].sort();
}

export function serviceWorkerBuild(html: string, fileNames: string[]): ServiceWorkerBuild {
  const fingerprint = createHash('sha256')
    .update([...fileNames].sort().join('\n'))
    .update('\0')
    .update(html)
    .digest('hex');
  return {
    version: fingerprint.slice(0, 16),
    shell: ['/index.html', ...shellAssetsFromHtml(html)],
  };
}

/**
 * Le script final : mode strict (la directive doit ouvrir le fichier pour
 * prendre effet), la constante injectée, puis le modèle inchangé.
 */
export function renderServiceWorker(
  build: ServiceWorkerBuild,
  template = readFileSync(TEMPLATE_PATH, 'utf-8'),
): string {
  return `'use strict';\nconst SW_BUILD = ${JSON.stringify(build)};\n${template}`;
}

export function serviceWorkerPlugin(): Plugin {
  return {
    name: 'teranga:service-worker',
    apply: 'build',
    // Après les plugins internes de Vite : index.html est alors déjà dans le bundle.
    enforce: 'post',
    generateBundle(_options, bundle) {
      const html = bundle['index.html'];
      if (!html || html.type !== 'asset' || typeof html.source !== 'string') {
        this.error('index.html introuvable dans le bundle : service worker impossible à générer.');
      }
      const build = serviceWorkerBuild(html.source, Object.keys(bundle));
      this.emitFile({
        type: 'asset',
        fileName: SERVICE_WORKER_FILE,
        source: renderServiceWorker(build),
      });
    },
  };
}
