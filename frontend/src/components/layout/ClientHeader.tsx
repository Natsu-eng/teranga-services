import React from 'react';
import { Link } from 'react-router';
import { useAuth } from '../../features/auth/hooks/useAuth';
import { firstNameOf } from '../../lib/identity';
import { Avatar } from '../ui/Avatar';
import { ButtonLink } from '../ui/Button';
import { LocationPicker } from './LocationPicker';

interface ClientHeaderProps {
  location: string;
  setLocation: (location: string) => void;
}

/**
 * En-tête de l'espace client : clair, aéré, localisation + salutation en
 * Fraunces. La salutation n'est PAS un titre (h1) : chaque écran porte son
 * propre titre, l'en-tête est commun à toutes les pages.
 * À droite : « Se connecter » pour un visiteur, l'avatar (accès au profil)
 * pour un compte connecté.
 */
export const ClientHeader: React.FC<ClientHeaderProps> = ({ location, setLocation }) => {
  const auth = useAuth();
  // Jamais de numéro de téléphone dans la salutation (comptes hérités).
  const name = firstNameOf(auth.user?.fullName);

  return (
    <header className="sticky top-0 z-40 bg-background/90 backdrop-blur-md">
      <div className="max-w-5xl mx-auto flex items-center justify-between gap-3 px-4 md:px-8 pt-3 pb-2">
        <div className="min-w-0">
          <LocationPicker location={location} setLocation={setLocation} />
          <p className="font-display text-display-sm font-semibold text-primary truncate">
            {name ? `Bonjour, ${name}` : 'Bonjour'}
          </p>
        </div>

        {auth.isAuthenticated && auth.user ? (
          <Link to="/profil" aria-label="Mon profil" className="shrink-0 rounded-full">
            <Avatar name={auth.user.fullName} size="sm" decorative />
          </Link>
        ) : (
          <ButtonLink to="/connexion" variant="outline" size="sm" className="shrink-0">
            Se connecter
          </ButtonLink>
        )}
      </div>
    </header>
  );
};
