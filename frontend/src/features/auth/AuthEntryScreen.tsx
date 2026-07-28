import React from 'react';
import { useLocation, useNavigate, type Location } from 'react-router';

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
    <main className="max-w-md mx-auto px-4 pt-20 pb-28 flex flex-col min-h-[calc(100vh-5rem)]">
      <div className="space-y-2 mb-10">
        <p className="font-sora text-xs font-semibold uppercase tracking-wider text-accent-foreground">
          Téranga Services
        </p>
        <h1 className="font-bold text-2xl text-primary">Bienvenue</h1>
        <p className="text-sm text-muted-foreground">
          Connectez-vous à votre compte, ou créez-en un pour trouver un artisan de confiance ou
          développer votre activité.
        </p>
      </div>

      <div className="mt-auto space-y-3">
        <button
          type="button"
          onClick={() => navigate('/connexion/telephone', { state: { intent: 'login', from } })}
          className="w-full h-14 rounded-full bg-primary text-white font-sora text-sm font-bold hover:opacity-90 active:scale-95 transition-all cursor-pointer"
        >
          Se connecter
        </button>
        <button
          type="button"
          onClick={() => navigate('/connexion/role', { state: { from } })}
          className="w-full h-14 rounded-full border-2 border-primary text-primary font-sora text-sm font-bold hover:bg-surface-muted active:scale-95 transition-all cursor-pointer"
        >
          Créer un compte
        </button>
      </div>
    </main>
  );
};
