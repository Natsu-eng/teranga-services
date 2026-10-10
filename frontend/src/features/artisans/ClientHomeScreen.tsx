import React, { useState } from 'react';
import { ArrowRight, Search, Sparkles, Users } from 'lucide-react';
import { Link, useNavigate } from 'react-router';
import { ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { ChipLink } from '../../components/ui/Chip';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { fieldClasses } from '../../components/ui/styles';
import type { ArtisanFilters } from '../../lib/api/types';
import { ArtisanCard, ArtisanCardSkeleton } from './components/ArtisanCard';
import { useArtisans } from './hooks/useArtisans';
import { useTrades } from './hooks/useTrades';

/**
 * Sélection affichée sur l'accueil : une première page courte, triée par
 * note côté serveur. Constante de module = référence stable entre les
 * rendus (useArtisans relance l'appel à chaque nouvelle référence).
 */
const RECOMMENDED_FILTERS: ArtisanFilters = { sort: 'rating', pageSize: 6 };

/**
 * Accueil de l'espace client (/accueil).
 *
 * Plus aucun filtrage en mémoire (dette AUDIT_PHASE2.md §6) : la barre de
 * recherche et les pastilles métier mènent à /recherche, qui interroge
 * l'API avec les filtres serveur (`q`, `trade`). L'accueil n'affiche que
 * la sélection recommandée renvoyée par le serveur.
 */
export const ClientHomeScreen: React.FC = () => {
  const navigate = useNavigate();
  const { data: artisans, isLoading, error, reload } = useArtisans(RECOMMENDED_FILTERS);
  const { data: trades } = useTrades();
  const [query, setQuery] = useState('');

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    navigate(trimmed ? `/recherche?q=${encodeURIComponent(trimmed)}` : '/recherche');
  };

  return (
    <main className="max-w-5xl mx-auto px-4 md:px-8 pt-2 space-y-7">
      <h1 className="sr-only">Trouver un artisan</h1>

      <form role="search" onSubmit={handleSearch} className="relative">
        <label htmlFor="accueil-recherche" className="sr-only">
          Rechercher un artisan
        </label>
        <Search
          aria-hidden
          className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground"
        />
        <input
          id="accueil-recherche"
          type="search"
          enterKeyHint="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Décrivez votre besoin…"
          className={fieldClasses({ className: 'h-14 pl-12 rounded-full shadow-card' })}
        />
      </form>

      {trades && trades.length > 0 && (
        <nav aria-label="Métiers" className="-mx-4 px-4 overflow-x-auto hide-scrollbar">
          <ul className="flex gap-2 pb-2 w-max">
            {trades.map((trade) => (
              <li key={trade.code}>
                <ChipLink to={`/recherche?trade=${encodeURIComponent(trade.code)}`}>
                  {trade.labelFr}
                </ChipLink>
              </li>
            ))}
          </ul>
        </nav>
      )}

      {/* Zone IA : surface vert très clair, signature des fonctions d'assistance. */}
      <Card
        tone="tint"
        padding="lg"
        as="section"
        aria-labelledby="assistant-ia"
        className="space-y-4"
      >
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-flex w-9 h-9 items-center justify-center rounded-full bg-surface text-primary-emerald shadow-card"
          >
            <Sparkles className="w-5 h-5" />
          </span>
          <p className="text-caption font-semibold uppercase tracking-[0.12em] text-primary-emerald">
            Assistant IA
          </p>
        </div>
        <h2 id="assistant-ia" className="font-display text-display-sm font-semibold text-primary">
          Décrivez votre problème, on vous trouve le bon artisan
        </h2>
        <ButtonLink
          to="/demande"
          variant="brand"
          trailingIcon={<ArrowRight aria-hidden className="w-4 h-4" />}
        >
          Essayer maintenant
        </ButtonLink>
      </Card>

      <section aria-labelledby="recommandes" className="space-y-4">
        <SectionHeader
          id="recommandes"
          title="Artisans recommandés"
          action={
            <Link
              to="/recherche"
              className="text-sm font-semibold text-primary-emerald underline-offset-4 hover:underline"
            >
              Voir tout
            </Link>
          }
        />

        {isLoading && artisans === null ? (
          <div className="space-y-3" aria-busy="true">
            {[0, 1, 2].map((key) => (
              <ArtisanCardSkeleton key={key} />
            ))}
          </div>
        ) : error && artisans === null ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : artisans && artisans.length === 0 ? (
          <EmptyState
            icon={<Users />}
            title="Aucun artisan disponible pour le moment."
            description="Décrivez votre besoin à notre assistant pour créer une demande."
          >
            <ButtonLink to="/demande" variant="outline" size="sm">
              Décrire mon problème
            </ButtonLink>
          </EmptyState>
        ) : (
          <ul className="space-y-3">
            {(artisans ?? []).map((artisan) => (
              <li key={artisan.id}>
                <ArtisanCard artisan={artisan} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
};
