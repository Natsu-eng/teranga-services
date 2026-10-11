import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, type Location } from 'react-router';
import type { AuthIntent, SignupRole } from '../../lib/api/auth-client';
import { Button } from '../../components/ui/Button';
import { TextField } from '../../components/ui/Field';
import { AuthShell } from './components/AuthShell';

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
    <AuthShell
      title="Comment vous appelez-vous ?"
      description={
        role === 'artisan'
          ? 'Ce nom sera affiché sur votre fiche publique, visible par les clients.'
          : 'Ce nom sera visible par les artisans que vous contactez.'
      }
      onBack={() => navigate('/connexion/role', { state: { from } })}
    >
      <form onSubmit={handleSubmit} className="flex-1 flex flex-col gap-6" noValidate>
        <TextField
          label="Nom complet"
          type="text"
          autoComplete="name"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          placeholder="Ex. Idrissa Diop"
          maxLength={MAX_LENGTH}
          error={error}
        />

        <Button type="submit" variant="brand" size="lg" fullWidth className="mt-auto">
          Continuer
        </Button>
      </form>
    </AuthShell>
  );
};
