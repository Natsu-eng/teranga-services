import React, { useState } from 'react';
import { AppView, Artisan } from '../types';

interface SearchScreenProps {
  artisans: Artisan[];
  setCurrentView: (view: AppView) => void;
  setSelectedArtisan: (artisan: Artisan) => void;
}

export const SearchScreen: React.FC<SearchScreenProps> = ({
  artisans,
  setCurrentView,
  setSelectedArtisan,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTrade, setSelectedTrade] = useState('Tous');
  const [minRating, setMinRating] = useState<number>(0);

  const trades = ['Tous', 'Plomberie', 'Électricité', 'Climatisation', 'Menuiserie'];

  const filtered = artisans.filter((art) => {
    const matchesSearch =
      !searchTerm ||
      art.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      art.trade.toLowerCase().includes(searchTerm.toLowerCase()) ||
      art.tags.some((t) => t.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchesTrade = selectedTrade === 'Tous' || art.trade.toLowerCase() === selectedTrade.toLowerCase();
    const matchesRating = art.rating >= minRating;

    return matchesSearch && matchesTrade && matchesRating;
  });

  return (
    <main className="max-w-4xl mx-auto px-4 md:px-8 pt-4 pb-28 space-y-6">
      <div className="flex items-center gap-3">
        <h2 className="font-bold text-2xl text-[#004129]">Recherche d'artisans</h2>
      </div>

      {/* Input */}
      <div className="relative">
        <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-[#707972]">
          search
        </span>
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Nom, spécialité (plombier, électricien...)"
          className="w-full h-14 pl-12 pr-4 rounded-full bg-[#f6f3f2] text-base text-[#1c1b1b] border-none outline-none focus:ring-2 focus:ring-[#004129]"
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
                ? 'bg-[#004129] text-white shadow-sm'
                : 'bg-[#f6f3f2] text-[#404943] hover:bg-[#eae7e7]'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Rating Filter */}
      <div className="flex items-center gap-2 text-xs font-sora text-[#404943]">
        <span className="font-semibold">Note minimale :</span>
        {[0, 4.5, 4.8].map((stars) => (
          <button
            key={stars}
            onClick={() => setMinRating(stars)}
            className={`px-3 py-1 rounded-full border transition-colors cursor-pointer ${
              minRating === stars
                ? 'border-[#004129] bg-[#004129]/10 text-[#004129] font-bold'
                : 'border-[#bfc9c1] text-[#707972]'
            }`}
          >
            {stars === 0 ? 'Toutes' : `${stars}+ ★`}
          </button>
        ))}
      </div>

      {/* Results List */}
      <div className="space-y-3">
        {filtered.map((art) => (
          <div
            key={art.id}
            onClick={() => {
              setSelectedArtisan(art);
              setCurrentView('artisan_profile');
            }}
            className="bg-white p-4 rounded-2xl artisan-shadow border border-[#eae7e7] flex gap-4 cursor-pointer hover:shadow-md transition-all"
          >
            <img src={art.avatarUrl} alt={art.name} className="w-20 h-20 rounded-2xl object-cover shrink-0" />
            <div className="flex-1 flex flex-col justify-between">
              <div>
                <div className="flex justify-between items-start">
                  <h4 className="font-bold text-base text-[#1c1b1b]">{art.name}</h4>
                  <div className="flex items-center gap-1 bg-[#ffddb1]/40 px-2 py-0.5 rounded-full">
                    <span className="material-symbols-outlined text-[#815600] text-[12px] fill-icon">
                      star
                    </span>
                    <span className="text-[#815600] font-sora text-xs font-bold">{art.rating}</span>
                  </div>
                </div>
                <p className="text-xs text-[#404943] font-sora font-medium mt-0.5">{art.trade}</p>
                <p className="text-xs text-[#707972] font-sora mt-1">{art.location} • {art.distance}</p>
              </div>

              <div className="flex justify-between items-center mt-2">
                <span className="text-[#004129] font-bold text-sm">{art.priceBase}</span>
                <span className="text-xs font-sora text-[#004129] font-bold flex items-center gap-1">
                  <span>Voir le profil</span>
                  <span className="material-symbols-outlined text-sm">arrow_forward</span>
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
};
