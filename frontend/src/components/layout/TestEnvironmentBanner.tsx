import React, { useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { fetchInstanceMeta, type InstanceMeta } from '../../lib/api/instance-meta';

/**
 * Bandeau « Version de test » (transparence de la beta).
 *
 * Affiché sur toute instance qui n'est PAS la production, d'après
 * l'environnement déclaré par le backend (`GET /api/v1/meta`) : une seule
 * source de vérité, impossible d'oublier une variable côté front.
 *
 * Sûr par défaut : tant que la réponse n'est pas arrivée, ou si l'appel
 * échoue, rien n'est affiché -- la production ne peut jamais montrer ce
 * bandeau par erreur. Discret : une fine ligne en haut de page, qui défile
 * avec le contenu, sans bouton ni fermeture.
 */
export const TestEnvironmentBanner: React.FC<{
  loadMeta?: () => Promise<InstanceMeta>;
}> = ({ loadMeta = fetchInstanceMeta }) => {
  const [environment, setEnvironment] = useState<InstanceMeta['environment'] | null>(null);

  useEffect(() => {
    let active = true;
    loadMeta()
      .then((meta) => {
        if (active) setEnvironment(meta.environment);
      })
      .catch(() => {
        // Backend injoignable : pas de bandeau (jamais d'affichage par défaut).
      });
    return () => {
      active = false;
    };
  }, [loadMeta]);

  if (environment === null || environment === 'production') return null;

  return (
    <div
      role="note"
      data-environment={environment}
      className="flex items-center justify-center gap-1.5 bg-accent-soft px-4 py-1 text-center text-xs font-medium text-accent-foreground"
    >
      <FlaskConical aria-hidden className="w-3.5 h-3.5 shrink-0" />
      <span>Version de test · données temporaires</span>
    </div>
  );
};
