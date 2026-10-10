import React from 'react';
import { AppBar } from '../../components/ui/AppBar';
import { ButtonLink } from '../../components/ui/Button';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { InterventionsList } from './InterventionsList';

/**
 * Suivi des interventions (/mes-interventions). GET /interventions/me
 * s'adapte au rôle côté serveur : l'écran reste donc lisible pour les deux,
 * mais l'artisan dispose de son propre espace (tableau de bord /pro) ; ici,
 * il garde le bandeau vert profond de l'espace Pro.
 */
export const InterventionsScreen: React.FC = () => {
  const auth = useAuth();
  const role = toDisplayRole(auth.role);
  const isPro = role === 'artisan';

  return (
    <>
      <AppBar
        title={isPro ? 'Mes demandes reçues' : 'Devis et travaux'}
        backTo={isPro ? '/pro' : '/profil'}
        tone={isPro ? 'pro' : 'light'}
      />
      <main className="w-full max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-10 space-y-4">
        {!isPro && (
          <p className="text-sm text-muted-foreground">
            Suivez vos mises en relation, acceptez les devis et notez les artisans une fois les
            travaux terminés.
          </p>
        )}
        <InterventionsList
          emptyTitle={
            isPro ? "Aucune demande reçue pour l'instant." : 'Aucun devis ni travaux en cours.'
          }
          emptyDescription={
            isPro
              ? undefined
              : 'Choisissez un artisan et demandez-lui un devis : le suivi apparaîtra ici.'
          }
          emptyAction={
            isPro ? undefined : (
              <ButtonLink to="/demande" variant="primary" size="sm">
                Décrire mon besoin
              </ButtonLink>
            )
          }
        />
      </main>
    </>
  );
};
