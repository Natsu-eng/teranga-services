import React from 'react';
import { ArrowRight, BadgeCheck, HeartHandshake, Star } from 'lucide-react';
import { useNavigate } from 'react-router';
import { UserRole } from '../../types';
import { SafeImage } from '../../components/ui/SafeImage';

interface LandingScreenProps {
  setUserRole: (role: UserRole) => void;
}

export const LandingScreen: React.FC<LandingScreenProps> = ({ setUserRole }) => {
  const navigate = useNavigate();

  return (
    <div className="bg-background text-foreground min-h-screen flex flex-col overflow-x-hidden">
      {/* Hero Illustration Section */}
      <section className="relative w-full h-[55vh] md:h-[62vh] overflow-hidden">
        <div className="absolute inset-0 w-full h-full">
          <SafeImage
            src="/images/hero-plombier.jpg"
            fallback="/images/placeholder-cover.svg"
            alt="Téranga Services Artisan"
            className="w-full h-full object-cover object-top scale-105 transition-transform duration-[3s] ease-out hover:scale-100"
          />
          <div className="absolute inset-0 hero-gradient"></div>
        </div>

        {/* Branding Float Header */}
        <div className="absolute top-6 left-0 w-full px-4 md:px-12 z-10 flex justify-between items-center">
          <div className="font-bold text-xl md:text-2xl text-primary flex items-center gap-2">
            <span className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center text-white text-sm font-bold">
              T
            </span>
            <span>Téranga Services</span>
          </div>

          <div className="bg-white/80 backdrop-blur-sm px-4 py-2 rounded-full shadow-sm flex items-center gap-2 border border-border-strong/30">
            <span className="w-2.5 h-2.5 rounded-full bg-accent-foreground animate-pulse"></span>
            <span className="font-sora text-xs text-muted-foreground font-medium">250+ Artisans Pro</span>
          </div>
        </div>
      </section>

      {/* Main Content Card */}
      <main className="flex-grow px-4 md:px-12 -mt-16 md:-mt-24 relative z-20 max-w-4xl mx-auto w-full flex flex-col items-center">
        <div className="w-full bg-background p-6 md:p-10 rounded-[32px] shadow-[0px_4px_20px_rgba(14,90,60,0.06)] text-center border border-border">
          <div className="mb-4 flex justify-center">
            <span className="px-4 py-1.5 rounded-full bg-accent-soft/40 text-accent-foreground font-sora text-xs font-semibold uppercase tracking-wider">
              L&apos;excellence au Sénégal
            </span>
          </div>

          <h1 className="font-headline-lg text-2xl md:text-4xl font-bold text-foreground mb-4 leading-tight max-w-lg mx-auto">
            Un artisan de confiance, en quelques secondes
          </h1>

          <p className="text-base md:text-lg text-muted-foreground mb-8 max-w-md mx-auto leading-relaxed">
            La première plateforme sénégalaise pour vos services à domicile. Qualité, ponctualité et
            respect assurés.
          </p>

          <div className="flex flex-col gap-3 items-center w-full max-w-xs mx-auto">
            <button
              onClick={() => {
                setUserRole('client');
                navigate('/accueil');
              }}
              className="w-full bg-primary-emerald text-white font-sora text-sm font-semibold py-4 rounded-full shadow-lg hover:brightness-110 active:scale-95 transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer"
            >
              <span>Commencer</span>
              <ArrowRight className="w-5 h-5" />
            </button>

            <button
              onClick={() => {
                setUserRole('artisan');
                navigate('/pro');
              }}
              className="w-full py-3 text-primary font-sora text-sm font-semibold hover:underline decoration-2 underline-offset-4 transition-all cursor-pointer"
            >
              Vous êtes artisan ?
            </button>
          </div>
        </div>

        {/* Trust Indicators */}
        <div className="mt-8 w-full grid grid-cols-1 md:grid-cols-3 gap-4 pb-12">
          <div className="flex items-center gap-4 p-4 rounded-2xl bg-white/60 border border-border-strong/20 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
              <BadgeCheck className="w-6 h-6" fill="currentColor" />
            </div>
            <div>
              <h3 className="font-sora text-sm font-bold text-foreground">Vérifiés</h3>
              <p className="font-sora text-xs text-muted-foreground">Profils authentifiés</p>
            </div>
          </div>

          <div className="flex items-center gap-4 p-4 rounded-2xl bg-white/60 border border-border-strong/20 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
              <HeartHandshake className="w-6 h-6" fill="currentColor" />
            </div>
            <div>
              <h3 className="font-sora text-sm font-bold text-foreground">Sécurisé</h3>
              <p className="font-sora text-xs text-muted-foreground">Paiement protégé</p>
            </div>
          </div>

          <div className="flex items-center gap-4 p-4 rounded-2xl bg-white/60 border border-border-strong/20 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
              <Star className="w-6 h-6" fill="currentColor" />
            </div>
            <div>
              <h3 className="font-sora text-sm font-bold text-foreground">Qualité 4.8/5</h3>
              <p className="font-sora text-xs text-muted-foreground">Avis de nos clients</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
