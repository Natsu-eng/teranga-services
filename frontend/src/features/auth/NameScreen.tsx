import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, type Location } from 'react-router';
import type { AuthIntent, SignupRole } from '../../lib/api/auth-client';

// Alignées sur `app/core/full_name.py` (FULL_NAME_MIN_LENGTH/MAX_LENGTH) --
// une seule source de vérité côté backend, ce contrôle local n'évite qu'un
// aller-retour pour un cas manifestement invalide.
const MIN_LENGTH = 2;
const MAX_LENGTH = 150;

interface NameLocationState {
  intent?: AuthIntent;
  role?: SignupRole;
  from?: Location;
}

/**
 * Saisie du nom, entre le choix du rôle et le numéro de téléphone
 * (BUILD_PLAN.md, fix confidentialité du contact) : le nom est requis pour
 * les deux rôles -- avant ce correctif, un compte se créait avec le
 * téléphone comme nom (visible publiquement sur la fiche artisan).
 * Uniquement en signup : le login ne passe jamais par cet écran.
 */
export const NameScreen: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const state = (location.state as NameLocationState | null) ?? {};
  const { intent, role, from } = state;

  const [fullName, setFullName] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Écran atteint directement (lien profond, rechargement) sans être passé
  // par RoleSelectScreen -- impossible de savoir pour quel rôle, on
  // recommence le parcours plutôt que de deviner (même garde que
  // PhoneScreen/OtpScreen).
  useEffect(() => {
    if (intent !== 'signup' || !role) navigate('/connexion', { replace: true });
  }, [intent, role, navigate]);

  if (intent !== 'signup' || !role) return null;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = fullName.trim();

    if (trimmed.length < MIN_LENGTH) {
      setError('Le nom est requis (au moins 2 caractères).');
      return;
    }
    if (trimmed.length > MAX_LENGTH) {
      setError(`Le nom est trop long (${MAX_LENGTH} caractères maximum).`);
      return;
    }

    setError(null);
    navigate('/connexion/telephone', { state: { intent, role, fullName: trimmed, from } });
  };

  return (
    <main className="max-w-md mx-auto px-4 pt-20 pb-28 space-y-6">
      <div className="space-y-2">
        <h1 className="font-bold text-2xl text-primary">Comment vous appelez-vous ?</h1>
        <p className="text-sm text-muted-foreground">
          {role === 'artisan'
            ? 'Ce nom sera affiché sur votre fiche publique, visible par les clients.'
            : 'Ce nom sera visible par les artisans que vous contactez.'}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <label className="block space-y-1.5">
          <span className="text-xs font-sora font-semibold text-muted-foreground">
            Nom complet
          </span>
          <input
            type="text"
            autoComplete="name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder="Ex. Idrissa Diop"
            maxLength={MAX_LENGTH}
            className="w-full h-14 px-4 rounded-full bg-surface-muted text-base text-foreground outline-none focus:ring-2 focus:ring-primary"
          />
        </label>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <button
          type="submit"
          className="w-full h-14 rounded-full bg-primary text-white font-sora text-sm font-bold hover:opacity-90 active:scale-95 transition-all cursor-pointer"
        >
          Continuer
        </button>
      </form>
    </main>
  );
};
