import React from 'react';
import { Compass } from 'lucide-react';
import { ButtonLink } from '../../components/ui/Button';

/**
 * Page 404. Sert aussi de réponse à tout compte non-admin sur /admin/*
 * (RequireAdminRoute) : elle doit donc rester strictement générique,
 * sans aucune mention d'un espace réservé.
 */
export const NotFoundScreen: React.FC = () => (
  <main className="min-h-screen bg-background flex flex-col items-center justify-center text-center px-4 py-24 gap-5">
    <span
      aria-hidden
      className="inline-flex w-20 h-20 items-center justify-center rounded-full bg-emerald-tint text-primary-emerald"
    >
      <Compass className="w-9 h-9" />
    </span>
    <div className="space-y-2">
      <h1 className="font-display text-display-md font-semibold text-primary">Page introuvable</h1>
      <p className="text-sm text-muted-foreground max-w-xs">
        Cette page n&apos;existe pas ou n&apos;est plus disponible.
      </p>
    </div>
    <ButtonLink to="/accueil" variant="brand">
      Retour à l&apos;accueil
    </ButtonLink>
  </main>
);
