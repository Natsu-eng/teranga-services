import React from 'react';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { InterventionsList } from './InterventionsList';
import { AppBar } from '../../components/ui/AppBar';

// Client-facing entry point (`/mes-interventions`). GET /interventions/me
// still adapts server-side to the caller's role (Lot 12a), so this stays
// role-aware for wording, but the artisan's own workspace now has its
// dedicated dashboard (ArtisanDashboardScreen, `/pro`, BUILD_PLAN.md §3.2)
// rather than being routed here.
export const InterventionsScreen: React.FC = () => {
  const auth = useAuth();
  const role = toDisplayRole(auth.role);

  return (
    <>
      <AppBar
        title={role === 'artisan' ? 'Mes demandes reçues' : 'Mes interventions'}
        backTo={role === 'artisan' ? '/pro' : '/profil'}
        tone={role === 'artisan' ? 'pro' : 'light'}
      />
      <main className="max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-28 space-y-6">
        <InterventionsList
          emptyTitle={
            role === 'artisan'
              ? "Aucune demande reçue pour l'instant."
              : 'Aucune intervention en cours.'
          }
        />
      </main>
    </>
  );
};
