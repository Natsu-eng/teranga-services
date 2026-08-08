import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, type Location } from 'react-router';
import { ApiError } from '../../lib/api';
import type { AuthIntent, SignupRole } from '../../lib/api/auth-client';
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
      setError(err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="max-w-md mx-auto px-4 pt-20 pb-28 space-y-6">
      <div className="space-y-2">
        <h1 className="font-bold text-2xl text-primary">
          {intent === 'signup' ? 'Créer votre compte' : 'Connexion'}
        </h1>
        <p className="text-sm text-muted-foreground">
          Entrez votre numéro de téléphone pour recevoir un code de vérification par SMS.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <label className="block space-y-1.5">
          <span className="text-xs font-sora font-semibold text-muted-foreground">Numéro de téléphone</span>
          <input
            type="tel"
            autoComplete="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="+221771234567"
            className="w-full h-14 px-4 rounded-full bg-surface-muted text-base text-foreground outline-none focus:ring-2 focus:ring-primary"
          />
        </label>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full h-14 rounded-full bg-primary text-white font-sora text-sm font-bold hover:opacity-90 active:scale-95 transition-all disabled:opacity-60 disabled:active:scale-100 cursor-pointer"
        >
          {isSubmitting ? 'Envoi en cours...' : 'Recevoir le code'}
        </button>
      </form>
    </main>
  );
};
