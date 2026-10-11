import React from 'react';
import { useLocation, useNavigate, type Location } from 'react-router';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { VerifiedBadge } from '../../components/ui/VerifiedBadge';
import { AuthShell } from './components/AuthShell';

/**
 * Point d'entrée du parcours auth : distingue explicitement Connexion et
 * Inscription (BUILD_PLAN.md §4) au lieu de sauter directement sur la
 * saisie du numéro. `from` (destination d'origine, posée par
 * `ProtectedRoute`/les écrans qui redirigent ici) traverse tout le parcours
 * jusqu'à `OtpScreen`, comme avant ce lot.
 */
export const AuthEntryScreen: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: Location } | null)?.from;

  return (
    <AuthShell
      title="Bienvenue"
      description="Connectez-vous à votre compte, ou créez-en un pour trouver un artisan de confiance ou développer votre activité."
    >
      <Card tone="tint" className="flex items-start gap-3">
        <VerifiedBadge size="md" />
        <p className="text-sm text-foreground">
          Chaque artisan est vérifié par notre équipe avant de pouvoir recevoir des demandes.
        </p>
      </Card>

      <div className="mt-auto pt-10 space-y-3">
        <Button
          variant="brand"
          size="lg"
          fullWidth
          onClick={() => navigate('/connexion/telephone', { state: { intent: 'login', from } })}
        >
          Se connecter
        </Button>
        <Button
          variant="outline"
          size="lg"
          fullWidth
          onClick={() => navigate('/connexion/role', { state: { from } })}
        >
          Créer un compte
        </Button>
      </div>
    </AuthShell>
  );
};
