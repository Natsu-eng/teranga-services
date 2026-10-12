import React from 'react';
import { Outlet } from 'react-router';
import { AdminHeader } from './AdminHeader';

/**
 * Coquille du back-office (/admin/*) : un en-tête et une navigation communs
 * aux huit sections, chaque écran ne rend que son contenu. La garde d'accès
 * (RequireAdminRoute) l'enveloppe dans le routage : un non-admin ne voit
 * jamais cette coquille, seulement l'écran « page introuvable ». Le serveur
 * reste le seul juge : chaque appel /admin/* y revérifie le rôle.
 */
export const AdminLayout: React.FC = () => (
  <div className="min-h-screen bg-background">
    <AdminHeader />
    <main className="max-w-5xl mx-auto px-4 md:px-8 pt-6 pb-16">
      <Outlet />
    </main>
  </div>
);
