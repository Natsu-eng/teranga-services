import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, type Location } from 'react-router';
import { ApiError } from '../../lib/api';
import type { AuthIntent, SignupRole } from '../../lib/api/auth-client';
import { Button } from '../../components/ui/Button';
import { TextField } from '../../components/ui/Field';
import { AuthShell } from './components/AuthShell';
import { useAuth } from './hooks/useAuth';

// Basic international format check (E.164-ish): '+' followed by 8 to 15
// digits. The backend is the authoritative validator/normalizer (E.164 via
// `phonenumbers`, BUILD_PLAN.md §4.1) — this only catches obviously
// malformed input before a round-trip.
const INTERNATIONAL_PHONE_REGEX = /^\+[1-9]\d{7,14}$/;

interface PhoneLocationState {
  intent?: AuthIntent;
  role?: SignupRole;
  fullName?: string;
  from?: Location;
}

export const PhoneScreen: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();

  const state = (location.state as PhoneLocationState | null) ?? {};
  const { intent, role, fullName, from } = state;

  const [phone, setPhone] = useState('+221');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Écran atteint directement (lien profond, rechargement) sans être passé
  // par AuthEntryScreen/RoleSelectScreen -- impossible de savoir s'il
  // s'agit d'une connexion ou d'une inscription (et quel rôle), on
  // recommence le parcours plutôt que de deviner.
  useEffect(() => {
    if (!intent) navigate('/connexion', { replace: true });
  }, [intent, navigate]);

  if (!intent) return null;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!INTERNATIONAL_PHONE_REGEX.test(phone)) {
      setError('Numéro invalide. Utilisez le format international, ex. +221771234567.');
      return;
    }

    setIsSubmitting(true);
    try {
      await auth.requestOtp(phone);
      navigate('/connexion/code', { state: { phone, intent, role, fullName, from } });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Retour vers l'étape précédente du parcours, état de navigation compris.
  const handleBack = () => {
    if (intent === 'signup') {
      navigate('/connexion/nom', { state: { intent, role, from } });
    } else {
      navigate('/connexion', { state: { from } });
    }
  };

  return (
    <AuthShell
      title={intent === 'signup' ? 'Créer votre compte' : 'Connexion'}
      description="Entrez votre numéro de téléphone pour recevoir un code de vérification par SMS."
      onBack={handleBack}
    >
      <form onSubmit={handleSubmit} className="flex-1 flex flex-col gap-6" noValidate>
        <TextField
          label="Numéro de téléphone"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
          placeholder="+221771234567"
          hint="Format international, sans espaces : +221 suivi de votre numéro."
          error={error}
        />

        <Button
          type="submit"
          variant="brand"
          size="lg"
          fullWidth
          isLoading={isSubmitting}
          className="mt-auto"
        >
          {isSubmitting ? 'Envoi en cours...' : 'Recevoir le code'}
        </Button>
      </form>
    </AuthShell>
  );
};
