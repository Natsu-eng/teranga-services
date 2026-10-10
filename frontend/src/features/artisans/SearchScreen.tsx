import React, { useEffect, useMemo, useState } from 'react';
import { MapPin, Search, SearchX, Star } from 'lucide-react';
import { useSearchParams } from 'react-router';
import { Card } from '../../components/ui/Card';
import { Chip } from '../../components/ui/Chip';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { fieldClasses } from '../../components/ui/styles';
import type { ArtisanFilters } from '../../lib/api/types';
import { ArtisanCard, ArtisanCardSkeleton } from './components/ArtisanCard';
import { useArtisans } from './hooks/useArtisans';
import { useTrades } from './hooks/useTrades';

/** Délai avant d'appliquer la saisie libre : un appel API par pause, pas par frappe. */
const SEARCH_DEBOUNCE_MS = 350;

/** Seuils de note proposés (la valeur part telle quelle en `min_rating`). */
const RATING_THRESHOLDS = [4, 4.5] as const;

/** Lit un nombre fini depuis l'URL ; toute valeur invalide est ignorée, jamais propagée. */
function finiteNumber(raw: string | null): number | undefined {
  if (raw == null || raw.trim() === '') return undefined;
  const value = Number(raw);
  return Number.isFinite(value) ? value : undefined;
}

/**
 * Recherche d'artisans (/recherche).
 *
 * Tout le filtrage est fait PAR LE SERVEUR (dette AUDIT_PHASE2.md §6 :
 * l'ancien écran filtrait en mémoire la première page reçue). L'état des
 * filtres vit dans l'URL — partageable, conservé au retour arrière :
 *   q      -> recherche libre (nom, présentation)       -> `q`
 *   trade  -> code métier                                -> `trade`
 *   note   -> note minimale                              -> `min_rating`
 *   lat/lng-> position (transmise par la demande IA)     -> `near`
 */
export const SearchScreen: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get('q')?.trim() ?? '';
  const tradeCode = searchParams.get('trade');
  const minRating = finiteNumber(searchParams.get('note'));
  const lat = finiteNumber(searchParams.get('lat'));
  const lng = finiteNumber(searchParams.get('lng'));
  const hasPosition = lat !== undefined && lng !== undefined;

  // Référence stable tant que les paramètres ne changent pas : useArtisans
  // ne relance l'appel qu'à un vrai changement de filtre. Aucun filtre ->
  // `undefined` (liste par défaut du serveur).
  const serverFilters = useMemo<ArtisanFilters | undefined>(() => {
    const near = lat !== undefined && lng !== undefined ? { lat, lng } : undefined;
    if (!tradeCode && !near && !q && minRating === undefined) return undefined;
    const filters: ArtisanFilters = { trade: tradeCode ?? undefined, near };
    if (q) filters.search = q;
    if (minRating !== undefined) filters.minRating = minRating;
    return filters;
  }, [tradeCode, lat, lng, q, minRating]);

  const { data: artisans, isLoading, error, reload } = useArtisans(serverFilters);
  const { data: trades } = useTrades();

  // Saisie locale, appliquée à l'URL après une pause (debounce).
  const [draft, setDraft] = useState(q);
  const [lastQ, setLastQ] = useState(q);
  // L'URL a changé par ailleurs (réinitialisation, retour arrière) : la
  // saisie se resynchronise (ajustement pendant le rendu, pattern React) —
  // sauf si elle correspond déjà, pour ne pas effacer l'espace que
  // l'utilisateur est en train de taper entre deux mots.
  if (q !== lastQ) {
    setLastQ(q);
    if (draft.trim() !== q) setDraft(q);
  }

  useEffect(() => {
    if (draft.trim() === q) return;
    const timer = setTimeout(() => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (draft.trim()) next.set('q', draft.trim());
          else next.delete('q');
          return next;
        },
        { replace: true },
      );
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [draft, q, setSearchParams]);

  const updateParam = (key: string, value: string | null) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value == null) next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  };

  // Réinitialise les filtres choisis ici ; la position transmise par la
  // demande IA est conservée (elle ne se ressaisit pas sur cet écran).
  const resetFilters = () => {
    setDraft('');
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams();
        for (const key of ['lat', 'lng']) {
          const value = prev.get(key);
          if (value != null) next.set(key, value);
        }
        return next;
      },
      { replace: true },
    );
  };

  const tradeLabel = trades?.find((trade) => trade.code === tradeCode)?.labelFr;

  return (
    <main className="max-w-5xl mx-auto px-4 md:px-8 pt-2 space-y-5">
      <SectionHeader as="h1" size="lg" title="Recherche d'artisans" />

      <form role="search" onSubmit={(event) => event.preventDefault()} className="relative">
        <label htmlFor="recherche-texte" className="sr-only">
          Nom ou spécialité
        </label>
        <Search
          aria-hidden
          className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground"
        />
        <input
          id="recherche-texte"
          type="search"
          enterKeyHint="search"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Nom, spécialité (plombier, électricien...)"
          className={fieldClasses({ className: 'h-14 pl-12 rounded-full shadow-card' })}
        />
      </form>

      {hasPosition && (
        <Card tone="tint" padding="sm" className="flex items-center gap-2 text-sm text-primary">
          <MapPin aria-hidden className="w-4 h-4 shrink-0" />
          <span>
            Artisans proches de vous
            {tradeLabel ? (
              <>
                {' '}
                pour <strong className="font-semibold">{tradeLabel}</strong>
              </>
            ) : null}
            , selon votre demande.
          </span>
        </Card>
      )}

      <div className="space-y-3">
        <div
          role="group"
          aria-label="Filtrer par métier"
          className="-mx-4 px-4 overflow-x-auto hide-scrollbar"
        >
          <div className="flex gap-2 pb-2 w-max">
            <Chip selected={!tradeCode} onClick={() => updateParam('trade', null)}>
              Tous
            </Chip>
            {(trades ?? []).map((trade) => (
              <Chip
                key={trade.code}
                selected={trade.code === tradeCode}
                onClick={() => updateParam('trade', trade.code)}
              >
                {trade.labelFr}
              </Chip>
            ))}
          </div>
        </div>

        <div role="group" aria-label="Note minimale" className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-muted-foreground">Note :</span>
          <Chip selected={minRating === undefined} onClick={() => updateParam('note', null)}>
            Toutes
          </Chip>
          {RATING_THRESHOLDS.map((threshold) => (
            <Chip
              key={threshold}
              selected={minRating === threshold}
              onClick={() => updateParam('note', String(threshold))}
              icon={
                <Star aria-hidden className="w-3.5 h-3.5" fill="currentColor" strokeWidth={0} />
              }
            >
              {String(threshold).replace('.', ',')} et plus
            </Chip>
          ))}
        </div>
      </div>

      <section aria-label="Résultats" aria-busy={isLoading} className="space-y-3">
        {isLoading && artisans === null ? (
          [0, 1, 2].map((key) => <ArtisanCardSkeleton key={key} />)
        ) : error && artisans === null ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : artisans && artisans.length === 0 ? (
          <EmptyState
            icon={<SearchX />}
            title="Aucun artisan ne correspond à ces critères."
            description="Élargissez votre recherche ou essayez un autre métier."
            action={{ label: 'Réinitialiser les filtres', onClick: resetFilters }}
          />
        ) : (
          <ul className="space-y-3">
            {(artisans ?? []).map((artisan) => (
              <li key={artisan.id}>
                <ArtisanCard artisan={artisan} headingLevel="h2" />
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
};
