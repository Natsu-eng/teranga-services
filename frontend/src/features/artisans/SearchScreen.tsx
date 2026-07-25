import React, { useState } from 'react';
import { Search, Star, ArrowRight, SearchX } from 'lucide-react';
import { Link } from 'react-router';
import { SafeImage } from '../../components/ui/SafeImage';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { useArtisans } from './hooks/useArtisans';
import { useTrades } from './hooks/useTrades';

export const SearchScreen: React.FC = () => {
  const { data: artisans, isLoading, error, reload } = useArtisans();
  const { data: tradesData } = useTrades();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTrade, setSelectedTrade] = useState('Tous');
  const [minRating, setMinRating] = useState<number>(0);

  const trades = ['Tous', ...(tradesData ?? []).map((trade) => trade.labelFr)];

  const filtered = (artisans ?? []).filter((art) => {
    const matchesSearch =
      !searchTerm ||
      art.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      art.trade.toLowerCase().includes(searchTerm.toLowerCase()) ||
      art.tags.some((t) => t.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchesTrade =
      selectedTrade === 'Tous' || art.trade.toLowerCase() === selectedTrade.toLowerCase();
    const matchesRating = art.rating >= minRating;

    return matchesSearch && matchesTrade && matchesRating;
  });

  return (
    <main className="max-w-4xl mx-auto px-4 md:px-8 pt-4 pb-28 space-y-6">
      <div className="flex items-center gap-3">
        <h2 className="font-bold text-2xl text-primary">Recherche d&apos;artisans</h2>
      </div>

      {/* Input */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground-soft w-6 h-6" />
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Nom, spécialité (plombier, électricien...)"
          className="w-full h-14 pl-12 pr-4 rounded-full bg-surface-muted text-base text-foreground border-none outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      {/* Filter Chips */}
      <div className="flex flex-wrap gap-2">
        {trades.map((t) => (
          <button
            key={t}
            onClick={() => setSelectedTrade(t)}
            className={`px-4 py-2 rounded-full font-sora text-xs font-semibold cursor-pointer transition-all ${
              selectedTrade === t
                ? 'bg-primary text-white shadow-sm'
                : 'bg-surface-muted text-muted-foreground hover:bg-border-subtle'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Rating Filter */}
      <div className="flex items-center gap-2 text-xs font-sora text-muted-foreground">
        <span className="font-semibold">Note minimale :</span>
        {[0, 4.5, 4.8].map((stars) => (
          <button
            key={stars}
            onClick={() => setMinRating(stars)}
            className={`px-3 py-1 rounded-full border transition-colors cursor-pointer ${
              minRating === stars
                ? 'border-primary bg-primary/10 text-primary font-bold'
                : 'border-border-strong text-muted-foreground-soft'
            }`}
          >
            {stars === 0 ? 'Toutes' : `${stars}+ ★`}
          </button>
        ))}
      </div>

      {/* Results List */}
      <div className="space-y-3">
        {isLoading && artisans === null ? (
          [0, 1, 2].map((key) => (
            <div key={key} className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle flex gap-4">
              <Skeleton className="w-20 h-20 rounded-2xl shrink-0" />
              <div className="flex-1 space-y-2 py-1">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-1/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          ))
        ) : error && artisans === null ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<SearchX className="text-muted-foreground-soft mb-2 w-9 h-9 mx-auto" />}
            title="Aucun artisan ne correspond à ces critères."
            action={{
              label: 'Réinitialiser les filtres',
              onClick: () => {
                setSearchTerm('');
                setSelectedTrade('Tous');
                setMinRating(0);
              },
            }}
          />
        ) : (
          filtered.map((art) => (
            <Link
              key={art.id}
              to={`/artisans/${art.id}`}
              className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle flex gap-4 cursor-pointer hover:shadow-md transition-all"
            >
              <SafeImage
                src={art.avatarUrl}
                fallback="/images/placeholder-avatar.svg"
                alt={art.name}
                className="w-20 h-20 rounded-2xl object-cover shrink-0"
              />
              <div className="flex-1 flex flex-col justify-between">
                <div>
                  <div className="flex justify-between items-start">
                    <h4 className="font-bold text-base text-foreground">{art.name}</h4>
                    <div className="flex items-center gap-1 bg-accent-soft/40 px-2 py-0.5 rounded-full">
                      <Star className="text-accent-foreground w-3 h-3" fill="currentColor" />
                      <span className="text-accent-foreground font-sora text-xs font-bold">{art.rating}</span>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground font-sora font-medium mt-0.5">{art.trade}</p>
                  <p className="text-xs text-muted-foreground-soft font-sora mt-1">
                    {art.location} • {art.distance}
                  </p>
                </div>

                <div className="flex justify-between items-center mt-2">
                  <span className="text-primary font-bold text-sm">{art.priceBase}</span>
                  <span className="text-xs font-sora text-primary font-bold flex items-center gap-1">
                    <span>Voir le profil</span>
                    <ArrowRight className="w-4 h-4" />
                  </span>
                </div>
              </div>
            </Link>
          ))
        )}
      </div>
    </main>
  );
};
