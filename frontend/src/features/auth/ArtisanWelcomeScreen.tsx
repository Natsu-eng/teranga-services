import React from 'react';
import { PartyPopper } from 'lucide-react';
import { useNavigate } from 'react-router';

/**
 * Accroche affichée une fois, juste après une inscription artisan
 * (BUILD_PLAN.md §4) : mène directement à l'onboarding (profil, métiers,
 * documents — BUILD_PLAN.md, onboarding artisan). Même langage visuel
 * `bg-primary` que `ArtisanDashboardScreen` pour prolonger l'identité
 * "Espace Pro" déjà amorcée sur `RoleSelectScreen`.
 */
export const ArtisanWelcomeScreen: React.FC = () => {
  const navigate = useNavigate();

  return (
    <main className="pb-28">
      <section className="bg-primary text-white px-4 md:px-8 pt-16 pb-12 rounded-b-3xl">
        <div className="max-w-md mx-auto text-center space-y-4">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-white/15 flex items-center justify-center">
            <PartyPopper className="w-8 h-8" />
          </div>
          <h1 className="font-headline-md text-2xl font-bold">Bienvenue chez Téranga Pro !</h1>
          <p className="text-sm text-primary-emerald-foreground">
            Votre compte artisan est créé. Complétez votre profil et envoyez vos documents pour
            être vérifié et commencer à recevoir des demandes.
          </p>
        </div>
      </section>

      <div className="max-w-md mx-auto px-4 pt-8">
        <button
          type="button"
          onClick={() => navigate('/pro/onboarding', { replace: true })}
          className="w-full h-14 rounded-full bg-primary text-white font-sora text-sm font-bold hover:opacity-90 active:scale-95 transition-all cursor-pointer"
        >
          Compléter mon profil
        </button>
      </div>
    </main>
  );
};
