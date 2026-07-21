import React, { useState } from 'react';
import { AppView, Artisan } from '../types';

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
          <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-[#404943]">
            search
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Décrivez votre besoin (ex: fuite, clim, électricité)..."
            className="w-full h-14 pl-12 pr-4 rounded-full border-none bg-[#f6f3f2] focus:ring-2 focus:ring-[#004129] text-base transition-all shadow-sm outline-none placeholder:text-[#707972]"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-[#707972] hover:text-[#1c1b1b]"
            >
              <span className="material-symbols-outlined">cancel</span>
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
                    ? 'bg-[#004129] text-white shadow-sm'
                    : 'bg-[#eae7e7] text-[#404943] hover:bg-[#0e5a3c] hover:text-white'
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
          className="relative overflow-hidden rounded-3xl bg-[#0e5a3c] p-6 md:p-8 group cursor-pointer active:scale-[0.98] transition-all shadow-md"
        >
          {/* Subtle Ambient Glow */}
          <div className="absolute -right-10 -bottom-10 w-48 h-48 bg-[#abf2ca]/20 rounded-full blur-2xl group-hover:scale-125 transition-transform"></div>

          <div className="relative z-10 space-y-4">
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 rounded-full bg-[#abf2ca]/20 flex items-center justify-center">
                <span className="material-symbols-outlined text-[#abf2ca] fill-icon">
                  auto_awesome
                </span>
              </div>
              <span className="text-[#8acfa9] font-sora text-xs font-bold uppercase tracking-wider">
                ASSISTANT IA
              </span>
            </div>

            <h2 className="font-bold text-xl md:text-3xl text-white leading-tight max-w-md">
              Décrivez votre problème, on vous trouve le bon artisan
            </h2>

            <div className="flex items-center gap-2 text-[#abf2ca] font-sora text-sm font-semibold group-hover:translate-x-1 transition-transform">
              <span>Essayer maintenant</span>
              <span className="material-symbols-outlined text-lg">arrow_forward</span>
            </div>
          </div>
        </div>
      </section>

      {/* Recommended Artisans Section */}
      <section className="space-y-4">
        <div className="flex justify-between items-end">
          <h3 className="font-bold text-xl text-[#004129]">Artisans recommandés</h3>
          <button
            onClick={() => setCurrentView('search')}
            className="text-[#004129] font-sora text-xs font-semibold hover:underline decoration-1 underline-offset-2"
          >
            Voir tout
          </button>
        </div>

        <div className="space-y-3">
          {filteredArtisans.length === 0 ? (
            <div className="bg-white rounded-2xl p-8 text-center border border-[#e5e2e1]">
              <span className="material-symbols-outlined text-4xl text-[#707972] mb-2">
                search_off
              </span>
              <p className="text-[#404943] font-medium">
                Aucun artisan ne correspond à votre recherche.
              </p>
              <button
                onClick={() => {
                  setSelectedCategory('Tout');
                  setSearchQuery('');
                }}
                className="mt-3 text-sm font-sora text-[#004129] underline"
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
                className="bg-white rounded-2xl p-4 flex gap-4 artisan-shadow border border-[#eae7e7] transition-all hover:translate-y-[-2px] hover:shadow-md cursor-pointer active:scale-[0.99]"
              >
                {/* Avatar */}
                <div className="relative flex-none">
                  <img
                    src={artisan.avatarUrl}
                    alt={artisan.name}
                    className="w-24 h-24 rounded-2xl object-cover"
                  />
                  {artisan.verified && (
                    <div className="absolute -bottom-1 -right-1 bg-white p-0.5 rounded-full shadow-sm">
                      <div className="bg-[#0e5a3c] p-1 rounded-full flex items-center justify-center">
                        <span className="material-symbols-outlined text-white text-[14px] fill-icon">
                          verified
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 flex flex-col justify-between py-0.5">
                  <div>
                    <div className="flex justify-between items-start">
                      <h4 className="font-bold text-base md:text-lg text-[#1c1b1b]">
                        {artisan.name}
                      </h4>
                      <div className="flex items-center gap-1 bg-[#ffddb1]/40 px-2 py-0.5 rounded-full border border-[#ffddb1]/60">
                        <span className="material-symbols-outlined text-[#815600] text-[14px] fill-icon">
                          star
                        </span>
                        <span className="text-[#815600] font-sora text-xs font-bold">
                          {artisan.rating}
                        </span>
                      </div>
                    </div>

                    <p className="text-[#404943] font-sora text-xs font-medium mt-0.5">
                      {artisan.trade}
                    </p>

                    <div className="flex items-center gap-2 mt-1">
                      <div className="flex items-center gap-0.5 text-[#707972] font-sora text-xs">
                        <span className="material-symbols-outlined text-[14px]">map</span>
                        <span>{artisan.distance}</span>
                      </div>
                      <span className="text-[#707972]">•</span>
                      <span className="text-[#404943] font-sora text-xs">
                        {artisan.reviewCount} avis
                      </span>
                    </div>
                  </div>

                  <div className="flex justify-between items-center mt-2">
                    <span className="text-[#004129] font-bold text-base">
                      {artisan.priceBase}{' '}
                      <span className="text-[#707972] font-normal text-xs">/base</span>
                    </span>
                    <span className="material-symbols-outlined text-[#0e5a3c] text-lg">
                      arrow_forward_ios
                    </span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {/* Téranga Premium Banner */}
      <section className="bg-[#f6f3f2] rounded-2xl p-5 md:p-6 flex items-center justify-between border border-[#e5e2e1]">
        <div className="space-y-1">
          <h4 className="font-bold text-base text-[#004129]">Téranga Premium</h4>
          <p className="text-[#404943] text-xs font-sora max-w-[220px] md:max-w-md">
            Accès prioritaire et garanties étendues sur tous vos travaux.
          </p>
        </div>
        <button
          onClick={() =>
            alert(
              'Téranga Premium vous offre la garantie sérénité 100% remboursement et un conseiller dédié à Dakar.',
            )
          }
          className="bg-[#004129] text-white px-4 py-2.5 rounded-full font-sora text-xs font-semibold hover:opacity-90 transition-all shrink-0 cursor-pointer"
        >
          Découvrir
        </button>
      </section>

      {/* Floating Action Button for AI */}
      <button
        onClick={() => setCurrentView('describe_problem')}
        className="fixed right-5 bottom-20 md:bottom-24 w-14 h-14 bg-[#004129] text-white rounded-full shadow-2xl flex items-center justify-center transition-transform hover:scale-110 active:scale-95 z-40 cursor-pointer"
        title="Poser votre question à l'IA"
      >
        <span className="material-symbols-outlined text-[26px] fill-icon">auto_awesome</span>
      </button>
    </main>
  );
};
