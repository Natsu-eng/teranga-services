import React, { useState } from 'react';
import {
  ArrowLeft,
  Share2,
  Heart,
  BadgeCheck,
  Star,
  CheckCircle2,
  Zap,
  Award,
  MessageCircle,
  Receipt,
} from 'lucide-react';
import { AppView, Artisan } from '../types';
import { SafeImage } from './ui/SafeImage';

interface ArtisanProfileScreenProps {
  artisan: Artisan;
  setCurrentView: (view: AppView) => void;
}

export const ArtisanProfileScreen: React.FC<ArtisanProfileScreenProps> = ({
  artisan,
  setCurrentView,
}) => {
  const [isFavorite, setIsFavorite] = useState(false);
  const [showShareNotification, setShowShareNotification] = useState(false);

  const handleShare = () => {
    navigator.clipboard?.writeText(window.location.href);
    setShowShareNotification(true);
    setTimeout(() => setShowShareNotification(false), 2500);
  };

  return (
    <div className="bg-background text-foreground min-h-screen pb-28">
      {/* Top Glass Header */}
      <header className="fixed top-0 left-0 right-0 z-50 glass-card border-b border-border-strong/30 px-4 h-16 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setCurrentView('client_home')}
            className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-surface-muted transition-colors active:scale-95 cursor-pointer"
          >
            <ArrowLeft className="text-foreground w-6 h-6" />
          </button>
          <h1 className="font-bold text-lg text-primary truncate">Profil Artisan</h1>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleShare}
            className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-surface-muted transition-colors cursor-pointer"
            title="Partager le profil"
          >
            <Share2 className="text-foreground w-6 h-6" />
          </button>
          <button
            onClick={() => setIsFavorite(!isFavorite)}
            className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-surface-muted transition-colors cursor-pointer"
            title="Ajouter aux favoris"
          >
            <Heart
              className={`w-6 h-6 ${isFavorite ? 'text-destructive' : 'text-foreground'}`}
              {...(isFavorite ? { fill: 'currentColor' } : {})}
            />
          </button>
        </div>
      </header>

      {showShareNotification && (
        <div className="fixed top-20 left-1/2 -translate-x-1/2 z-50 bg-primary text-white px-4 py-2 rounded-full text-xs font-sora shadow-lg animate-in fade-in slide-in-from-top-2">
          Lien du profil copié !
        </div>
      )}

      <main className="w-full">
        {/* Cover Photo */}
        <section className="relative w-full h-60 md:h-80">
          <div className="w-full h-full bg-border overflow-hidden">
            <SafeImage
              src={artisan.coverUrl}
              fallback="/images/placeholder-cover.svg"
              alt="Atelier artisan"
              className="w-full h-full object-cover"
            />
          </div>

          {/* Profile Picture Overlap */}
          <div className="absolute -bottom-14 left-4 md:left-12 ring-4 ring-background rounded-full overflow-hidden w-28 h-28 md:w-36 md:h-36 bg-white artisan-shadow">
            <SafeImage
              src={artisan.avatarUrl}
              fallback="/images/placeholder-avatar.svg"
              alt={artisan.name}
              className="w-full h-full object-cover"
            />
          </div>
        </section>

        {/* Basic Info */}
        <section className="mt-16 px-4 md:px-12 max-w-4xl mx-auto">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <h2 className="font-bold text-2xl md:text-3xl text-primary">{artisan.name}</h2>
              {artisan.verified && (
                <div className="flex items-center gap-1 bg-accent-soft/40 text-accent-foreground px-2.5 py-0.5 rounded-full border border-accent-soft">
                  <BadgeCheck className="w-[14px] h-[14px]" fill="currentColor" />
                  <span className="text-xs font-sora font-semibold">Vérifié</span>
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-2 my-1">
              {artisan.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-3 py-1 bg-surface-muted border border-border-strong/40 rounded-full font-sora text-xs text-muted-foreground font-medium"
                >
                  {tag}
                </span>
              ))}
            </div>

            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="flex items-center text-accent-foreground">
                <Star className="w-[18px] h-[18px]" fill="currentColor" />
                <span className="font-sora font-bold ml-1">{artisan.rating}</span>
              </div>
              <span>({artisan.reviewCount} avis)</span>
              <span className="w-1 h-1 rounded-full bg-border-strong" />
              <span>{artisan.location}</span>
            </div>
          </div>
        </section>

        {/* Stats Row */}
        <section className="mt-6 px-4 md:px-12 max-w-4xl mx-auto">
          <div className="grid grid-cols-3 gap-4 py-5 border-y border-border-strong/30">
            <div className="flex flex-col items-center text-center">
              <CheckCircle2 className="text-primary mb-1 w-8 h-8 md:w-9 md:h-9" />
              <span className="font-bold text-xl text-primary">{artisan.stats.chantiers}</span>
              <span className="text-[11px] font-sora text-muted-foreground uppercase tracking-wider font-semibold">
                Chantiers
              </span>
            </div>

            <div className="flex flex-col items-center text-center">
              <Zap className="text-primary mb-1 w-8 h-8 md:w-9 md:h-9" />
              <span className="font-bold text-xl text-primary">{artisan.stats.responseTime}</span>
              <span className="text-[11px] font-sora text-muted-foreground uppercase tracking-wider font-semibold">
                Réponse
              </span>
            </div>

            <div className="flex flex-col items-center text-center">
              <Award className="text-primary mb-1 w-8 h-8 md:w-9 md:h-9" />
              <span className="font-bold text-xl text-primary">{artisan.stats.experience}</span>
              <span className="text-[11px] font-sora text-muted-foreground uppercase tracking-wider font-semibold">
                D&apos;exp.
              </span>
            </div>
          </div>
        </section>

        {/* Bio Section */}
        <section className="mt-6 px-4 md:px-12 max-w-4xl mx-auto space-y-2">
          <h3 className="font-bold text-xl text-primary">À propos</h3>
          <p className="text-base text-muted-foreground leading-relaxed">{artisan.bio}</p>
        </section>

        {/* Realisations Gallery */}
        <section className="mt-8">
          <div className="px-4 md:px-12 max-w-4xl mx-auto flex justify-between items-center mb-3">
            <h3 className="font-bold text-xl text-primary">Réalisations</h3>
            <button className="text-primary font-sora text-xs font-semibold hover:underline">
              Voir tout
            </button>
          </div>

          <div className="flex gap-4 overflow-x-auto hide-scrollbar px-4 md:px-12 max-w-4xl mx-auto pb-2">
            {artisan.realisations.map((real) => (
              <div
                key={real.id}
                className="flex-shrink-0 w-64 md:w-80 h-48 rounded-2xl overflow-hidden artisan-shadow border border-border group relative"
              >
                <SafeImage
                  src={real.imageUrl}
                  fallback="/images/placeholder-cover.svg"
                  alt={real.altText}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-90 p-4 flex items-end">
                  <p className="text-white font-sora text-xs font-semibold">{real.title}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Customer Reviews */}
        <section className="mt-8 px-4 md:px-12 max-w-4xl mx-auto space-y-4">
          <h3 className="font-bold text-xl text-primary">Avis clients</h3>

          <div className="space-y-3">
            {artisan.reviews.map((rev) => (
              <div
                key={rev.id}
                className="p-5 bg-surface-muted rounded-2xl border border-border-strong/20 shadow-sm"
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-primary/15 flex items-center justify-center text-primary font-bold font-sora text-sm">
                      {rev.avatarInitials}
                    </div>
                    <div>
                      <h4 className="font-sora text-sm font-bold text-foreground">{rev.author}</h4>
                      <div className="flex text-accent-foreground text-sm">
                        {[...Array(rev.rating)].map((_, i) => (
                          <Star key={i} className="w-[14px] h-[14px]" fill="currentColor" />
                        ))}
                      </div>
                    </div>
                  </div>
                  <span className="font-sora text-xs text-muted-foreground-soft">{rev.date}</span>
                </div>
                <p className="text-sm text-muted-foreground italic leading-relaxed">{rev.comment}</p>
              </div>
            ))}
          </div>

          <button
            onClick={() => alert('Affichage des 120 avis vérifiés par Téranga Services...')}
            className="w-full py-3.5 rounded-full border-1.5 border-primary text-primary font-sora text-sm font-semibold hover:bg-surface-muted transition-colors cursor-pointer"
          >
            Voir les {artisan.reviewCount} avis
          </button>
        </section>
      </main>

      {/* Bottom Sticky Action Bar */}
      <div className="fixed bottom-0 left-0 right-0 glass-card border-t border-border-strong/30 p-4 z-50">
        <div className="max-w-xl mx-auto flex gap-3">
          <button
            onClick={() => setCurrentView('chat')}
            className="flex-1 h-14 rounded-full border-1.5 border-primary text-primary font-sora text-sm font-bold flex items-center justify-center gap-2 hover:bg-surface-muted active:scale-95 transition-all cursor-pointer"
          >
            <MessageCircle className="w-6 h-6" />
            <span>Message</span>
          </button>

          <button
            onClick={() => setCurrentView('chat')}
            className="flex-[1.5] h-14 rounded-full bg-accent-alt text-accent-alt-foreground font-sora text-sm font-bold shadow-md flex items-center justify-center gap-2 hover:brightness-105 active:scale-95 transition-all cursor-pointer"
          >
            <Receipt className="w-6 h-6" fill="currentColor" />
            <span>Demander un devis</span>
          </button>
        </div>
      </div>
    </div>
  );
};
