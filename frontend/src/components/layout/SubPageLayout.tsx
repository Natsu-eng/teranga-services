import React from 'react';
import { Outlet } from 'react-router';

/**
 * Gabarit des sous-pages (fiche artisan, demande IA, mes demandes, mes
 * interventions, onboarding Pro) : ni en-tête commun ni navigation basse.
 * Chaque écran pose son propre AppBar (titre + retour), et éventuellement
 * sa barre d'actions en bas — qui ne se superpose ainsi jamais à la
 * navigation principale.
 */
export const SubPageLayout: React.FC = () => (
  <div className="min-h-screen bg-background text-foreground flex flex-col">
    <Outlet />
  </div>
);
