import React, { useState } from 'react';
import {
  Search,
  CircleX,
  Sparkles,
  ArrowRight,
  SearchX,
  BadgeCheck,
  Star,
  Map,
  ChevronRight,
} from 'lucide-react';
import { AppView, Artisan } from '../../types';
import { SafeImage } from '../../components/ui/SafeImage';

interface ClientHomeScreenProps {
  artisans: Artisan[];
  setCurrentView: (view: AppView) => void;
  setSelectedArtisan: (artisan: Artisan) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
}

export const ClientHomeScreen: React.FC<ClientHomeScreenProps> = ({
  artisans,
  setCurrentView,
  setSelectedArtisan,
  searchQuery,
  setSearchQuery,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('Tout');

  const categories = [
    'Tout',
    'Plomberie',
    'Électricité',
    'Climatisation',
    'Menuiserie',
    'Maçonnerie',
    'Peinture',
  ];

  const filteredArtisans = artisans.filter((artisan) => {
    const matchesCategory =
      selectedCategory === 'Tout' || artisan.trade.toLowerCase() === selectedCategory.toLowerCase();
    const matchesSearch =
      !searchQuery ||
      artisan.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      artisan.trade.toLowerCase().includes(searchQuery.toLowerCase()) ||
      artisan.tags.some((tag) => tag.toLowerCase().includes(searchQuery.toLowerCase()));

    return matchesCategory && matchesSearch;
  });

  return (
    <main className="max-w-5xl mx-auto px-4 md:px-8 pt-4 pb-28 space-y-6">
      {/* Search Bar */}
      <section className="relative">
        <div className="relative group">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground w-6 h-6" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Décrivez votre besoin (ex: fuite, clim, électricité)..."
            className="w-full h-14 pl-12 pr-4 rounded-full border-none bg-surface-muted focus:ring-2 focus:ring-primary text-base transition-all shadow-sm outline-none placeholder:text-muted-foreground-soft"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground-soft hover:text-foreground"
            >
              <CircleX className="w-6 h-6" />
            </button>
          )}
        </div>
      </section>

      {/* Categories Horizontal Scroll */}
      <section className="-mx-4 px-4 overflow-x-auto hide-scrollbar">
        <div className="flex gap-2.5 pb-2">
          {categories.map((cat) => {
            const isActive = selectedCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`flex-none px-6 py-2 rounded-full font-sora text-xs font-semibold transition-all cursor-pointer ${
                  isActive
                    ? 'bg-primary text-white shadow-sm'
                    : 'bg-border-subtle text-muted-foreground hover:bg-primary-emerald hover:text-white'
                }`}
              >
                {cat}
              </button>
            );
          })}
        </div>
      </section>

      {/* AI Assistant Feature Bento Card */}
      <section>
        <div
          onClick={() => setCurrentView('describe_problem')}
          className="relative overflow-hidden rounded-3xl bg-primary-emerald p-6 md:p-8 group cursor-pointer active:scale-[0.98] transition-all shadow-md"
        >
          {/* Subtle Ambient Glow */}
          <div className="absolute -right-10 -bottom-10 w-48 h-48 bg-success/20 rounded-full blur-2xl group-hover:scale-125 transition-transform"></div>

          <div className="relative z-10 space-y-4">
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 rounded-full bg-success/20 flex items-center justify-center">
                <Sparkles className="text-success w-6 h-6" fill="currentColor" />
              </div>
              <span className="text-primary-emerald-foreground font-sora text-xs font-bold uppercase tracking-wider">
                ASSISTANT IA
              </span>
            </div>

            <h2 className="font-bold text-xl md:text-3xl text-white leading-tight max-w-md">
              Décrivez votre problème, on vous trouve le bon artisan
            </h2>

            <div className="flex items-center gap-2 text-success font-sora text-sm font-semibold group-hover:translate-x-1 transition-transform">
              <span>Essayer maintenant</span>
              <ArrowRight className="w-[18px] h-[18px]" />
            </div>
          </div>
        </div>
      </section>

      {/* Recommended Artisans Section */}
      <section className="space-y-4">
        <div className="flex justify-between items-end">
          <h3 className="font-bold text-xl text-primary">Artisans recommandés</h3>
          <button
            onClick={() => setCurrentView('search')}
            className="text-primary font-sora text-xs font-semibold hover:underline decoration-1 underline-offset-2"
          >
            Voir tout
          </button>
        </div>

        <div className="space-y-3">
          {filteredArtisans.length === 0 ? (
            <div className="bg-white rounded-2xl p-8 text-center border border-border">
              <SearchX className="text-muted-foreground-soft mb-2 w-9 h-9 mx-auto" />
              <p className="text-muted-foreground font-medium">
                Aucun artisan ne correspond à votre recherche.
              </p>
              <button
                onClick={() => {
                  setSelectedCategory('Tout');
                  setSearchQuery('');
                }}
                className="mt-3 text-sm font-sora text-primary underline"
              >
                Réinitialiser les filtres
              </button>
            </div>
          ) : (
            filteredArtisans.map((artisan) => (
              <div
                key={artisan.id}
                onClick={() => {
                  setSelectedArtisan(artisan);
                  setCurrentView('artisan_profile');
                }}
                className="bg-white rounded-2xl p-4 flex gap-4 artisan-shadow border border-border-subtle transition-all hover:translate-y-[-2px] hover:shadow-md cursor-pointer active:scale-[0.99]"
              >
                {/* Avatar */}
                <div className="relative flex-none">
                  <SafeImage
                    src={artisan.avatarUrl}
                    fallback="/images/placeholder-avatar.svg"
                    alt={artisan.name}
                    className="w-24 h-24 rounded-2xl object-cover"
                  />
                  {artisan.verified && (
                    <div className="absolute -bottom-1 -right-1 bg-white p-0.5 rounded-full shadow-sm">
                      <div className="bg-primary-emerald p-1 rounded-full flex items-center justify-center">
                        <BadgeCheck className="text-white w-[14px] h-[14px]" fill="currentColor" />
                      </div>
                    </div>
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 flex flex-col justify-between py-0.5">
                  <div>
                    <div className="flex justify-between items-start">
                      <h4 className="font-bold text-base md:text-lg text-foreground">
                        {artisan.name}
                      </h4>
                      <div className="flex items-center gap-1 bg-accent-soft/40 px-2 py-0.5 rounded-full border border-accent-soft/60">
                        <Star className="text-accent-foreground w-[14px] h-[14px]" fill="currentColor" />
                        <span className="text-accent-foreground font-sora text-xs font-bold">
                          {artisan.rating}
                        </span>
                      </div>
                    </div>

                    <p className="text-muted-foreground font-sora text-xs font-medium mt-0.5">
                      {artisan.trade}
                    </p>

                    <div className="flex items-center gap-2 mt-1">
                      <div className="flex items-center gap-0.5 text-muted-foreground-soft font-sora text-xs">
                        <Map className="w-[14px] h-[14px]" />
                        <span>{artisan.distance}</span>
                      </div>
                      <span className="text-muted-foreground-soft">•</span>
                      <span className="text-muted-foreground font-sora text-xs">
                        {artisan.reviewCount} avis
                      </span>
                    </div>
                  </div>

                  <div className="flex justify-between items-center mt-2">
                    <span className="text-primary font-bold text-base">
                      {artisan.priceBase}{' '}
                      <span className="text-muted-foreground-soft font-normal text-xs">/base</span>
                    </span>
                    <ChevronRight className="text-primary-emerald w-[18px] h-[18px]" />
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {/* Téranga Premium Banner */}
      <section className="bg-surface-muted rounded-2xl p-5 md:p-6 flex items-center justify-between border border-border">
        <div className="space-y-1">
          <h4 className="font-bold text-base text-primary">Téranga Premium</h4>
          <p className="text-muted-foreground text-xs font-sora max-w-[220px] md:max-w-md">
            Accès prioritaire et garanties étendues sur tous vos travaux.
          </p>
        </div>
        <button
          onClick={() =>
            alert(
              'Téranga Premium vous offre la garantie sérénité 100% remboursement et un conseiller dédié à Dakar.',
            )
          }
          className="bg-primary text-white px-4 py-2.5 rounded-full font-sora text-xs font-semibold hover:opacity-90 transition-all shrink-0 cursor-pointer"
        >
          Découvrir
        </button>
      </section>

      {/* Floating Action Button for AI */}
      <button
        onClick={() => setCurrentView('describe_problem')}
        className="fixed right-5 bottom-20 md:bottom-24 w-14 h-14 bg-primary text-white rounded-full shadow-2xl flex items-center justify-center transition-transform hover:scale-110 active:scale-95 z-40 cursor-pointer"
        title="Poser votre question à l'IA"
      >
        <Sparkles className="w-[26px] h-[26px]" fill="currentColor" />
      </button>
    </main>
  );
};
