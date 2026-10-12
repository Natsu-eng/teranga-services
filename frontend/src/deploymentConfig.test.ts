import { readFileSync } from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';

/**
 * Le front a deux hébergements possibles (DEPLOYMENT.md) : Vercel
 * (vercel.json) et Railway (Caddyfile). Leurs en-têtes de sécurité doivent
 * rester IDENTIQUES : une CSP modifiée d'un côté seulement ouvrirait une
 * faille, ou casserait le site, sur un seul des deux.
 */
const root = path.resolve(__dirname, '..');

function vercelHeaders(): Record<string, string> {
  const config = JSON.parse(readFileSync(path.join(root, 'vercel.json'), 'utf-8')) as {
    headers: { source: string; headers: { key: string; value: string }[] }[];
  };
  const global = config.headers.find((rule) => rule.source === '/(.*)');
  return Object.fromEntries((global?.headers ?? []).map(({ key, value }) => [key, value]));
}

function caddyHeaders(): Record<string, string> {
  const caddyfile = readFileSync(path.join(root, 'Caddyfile'), 'utf-8');
  const block = /\n\theader \{\n([\s\S]*?)\n\t\}/.exec(caddyfile);
  if (!block) throw new Error('Bloc « header { ... } » introuvable dans le Caddyfile.');
  return Object.fromEntries(
    block[1]
      .split('\n')
      .map((line) => /^\s*([A-Za-z-]+) "(.*)"$/.exec(line))
      .filter((match): match is RegExpExecArray => match !== null)
      .map((match) => [match[1], match[2]]),
  );
}

describe('configuration de déploiement du front', () => {
  it('sert les mêmes en-têtes de sécurité sur Railway (Caddy) que sur Vercel', () => {
    const vercel = vercelHeaders();
    const caddy = caddyHeaders();

    expect(Object.keys(vercel).length).toBeGreaterThanOrEqual(5);
    for (const [name, value] of Object.entries(vercel)) {
      expect(caddy[name], name).toBe(value);
    }
    // HSTS : posé par Caddy ; Vercel l'applique lui-même au niveau de la plateforme.
    expect(caddy['Strict-Transport-Security']).toMatch(/^max-age=\d+/);
  });

  it('ne fige jamais une URL de backend en dur dans les fichiers de déploiement', () => {
    for (const file of ['Dockerfile', 'Caddyfile', 'vercel.json', 'railway.json']) {
      const content = readFileSync(path.join(root, file), 'utf-8');
      expect(content, file).not.toMatch(/https?:\/\/[a-z0-9.-]+\.(?:railway\.app|up\.railway)/i);
      expect(content, file).not.toMatch(/localhost:8000/);
    }
  });
});
