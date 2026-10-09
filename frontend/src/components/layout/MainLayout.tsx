import React from 'react';
import { Outlet } from 'react-router';
import { useAuth } from '../../features/auth/hooks/useAuth';
import { toDisplayRole } from '../../features/auth/role';
import { ClientBottomNav, ProBottomNav } from './BottomNav';
import { ClientHeader } from './ClientHeader';
import { ProHeader } from './ProHeader';
import { SkipLink } from './SkipLink';

interface MainLayoutProps {
  location: string;
  setLocation: (location: string) => void;
}

/**
 * Coque des écrans « onglets » (accueil, recherche, messages, profil,
 * tableau de bord Pro). L'habillage suit le rôle du compte connecté,
 * toujours dérivé du serveur (auth.role) :
 * - client / visiteur : en-tête clair + navigation 4 entrées ;
 * - artisan           : bandeau vert profond + navigation Pro 3 entrées.
 * Le contenu réserve la hauteur de la barre basse (pb-28) : aucun élément
 * n'est jamais masqué sous la navigation.
 */
export const MainLayout: React.FC<MainLayoutProps> = ({ location, setLocation }) => {
  const auth = useAuth();
  const isPro = toDisplayRole(auth.role) === 'artisan';

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <SkipLink />
      {isPro ? <ProHeader /> : <ClientHeader location={location} setLocation={setLocation} />}
      <div id="contenu" tabIndex={-1} className="flex-1 pb-28 focus:outline-none">
        <Outlet />
      </div>
      {isPro ? <ProBottomNav /> : <ClientBottomNav />}
    </div>
  );
};
