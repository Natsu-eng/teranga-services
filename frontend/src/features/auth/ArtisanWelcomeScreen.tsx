import React from 'react';
import { ArrowRight, FileCheck2, UserRound, Wrench } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Button } from '../../components/ui/Button';
import { Logo } from '../../components/ui/Logo';

const NEXT_STEPS = [
  { icon: UserRound, label: 'Complétez votre profil (photo, présentation, expérience)' },
  { icon: Wrench, label: 'Déclarez vos métiers, vos tarifs et votre zone' },
  { icon: FileCheck2, label: "Envoyez vos documents d'identité pour être vérifié" },
] as const;

/**
 * Accroche affichée une fois, juste après une inscription artisan
 * (BUILD_PLAN.md §4) : plein écran vert profond — la couleur de l'espace
 * Pro — et une seule action, mener à l'onboarding.
 */
export const ArtisanWelcomeScreen: React.FC = () => {
  const navigate = useNavigate();

  return (
    <main data-tone="dark" className="min-h-screen bg-primary text-white flex flex-col">
      <div className="max-w-md w-full mx-auto px-4 pt-6 pb-10 flex-1 flex flex-col">
        <Logo variant="pro" tone="on-dark" />

        <div className="pt-14 space-y-4">
          <p className="text-caption font-semibold uppercase tracking-[0.14em] text-accent">
            Compte artisan créé
          </p>
          <h1 className="font-display text-display-lg font-semibold">
            Bienvenue chez Téranga Pro !
          </h1>
          <p className="text-base text-primary-emerald-foreground">
            Votre compte artisan est créé. Complétez votre profil et envoyez vos documents pour être
            vérifié et commencer à recevoir des demandes.
          </p>
        </div>

        <ol className="mt-10 space-y-3">
          {NEXT_STEPS.map(({ icon: Icon, label }, index) => (
            <li key={label} className="flex items-center gap-3 rounded-card bg-white/10 p-4">
              <span
                aria-hidden
                className="shrink-0 inline-flex w-9 h-9 items-center justify-center rounded-full bg-accent text-primary"
              >
                <Icon className="w-5 h-5" />
              </span>
              <span className="text-sm">
                <span className="sr-only">Étape {index + 1} : </span>
                {label}
              </span>
            </li>
          ))}
        </ol>

        <Button
          variant="primary"
          size="lg"
          fullWidth
          className="mt-auto"
          trailingIcon={<ArrowRight aria-hidden className="w-5 h-5" />}
          onClick={() => navigate('/pro/onboarding', { replace: true })}
        >
          Compléter mon profil
        </Button>
      </div>
    </main>
  );
};
