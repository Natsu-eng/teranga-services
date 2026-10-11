import React from 'react';
import { Outlet } from 'react-router';

/**
 * Gabarit nu (accueil marketing, parcours de connexion, bienvenue artisan,
 * espace admin) : l'écran gère seul sa mise en page, sans navigation de
 * l'application autour.
 */
export const MinimalLayout: React.FC = () => (
  <div className="min-h-screen bg-background text-foreground flex flex-col">
    <div className="flex-1">
      <Outlet />
    </div>
  </div>
);
