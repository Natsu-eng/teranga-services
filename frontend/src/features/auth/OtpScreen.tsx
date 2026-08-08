import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, type Location } from 'react-router';
import { ApiError } from '../../lib/api';
import type { AuthIntent, SignupRole } from '../../lib/api/auth-client';
import { useAuth } from './hooks/useAuth';

const RESEND_DELAY_SECONDS = 30;
const CODE_LENGTH = 6;

interface OtpLocationState {
  phone?: string;
  intent?: AuthIntent;
  role?: SignupRole;
  fullName?: string;
  from?: Location;
}

export const OtpScreen: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();

  const state = (location.state as OtpLocationState | null) ?? {};
  const { phone, intent, role, fullName } = state;

  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(RESEND_DELAY_SECONDS);

  // Absence de `phone`/`intent` dans l'état = écran atteint directement
  // (lien profond, rechargement) plutôt que via l'étape numéro -- on
  // recommence le parcours plutôt que d'afficher un écran cassé ("code
  // envoyé à undefined") ou de deviner connexion vs inscription.
  useEffect(() => {
    if (!phone || !intent) navigate('/connexion', { replace: true });
  }, [phone, intent, navigate]);

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const timer = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [secondsLeft]);

  if (!phone || !intent) return null;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!/^\d{6}$/.test(code)) {
      setError('Le code doit contenir 6 chiffres.');
      return;
    }

    setIsSubmitting(true);
    try {
      if (intent === 'signup') {
        await auth.signup(phone, code, role ?? 'client', fullName ?? '');
      } else {
        await auth.login(phone, code);
      }
      if (intent === 'signup' && role === 'artisan') {
        navigate('/bienvenue-artisan', { replace: true });
      } else {
        navigate(state.from?.pathname ?? '/profil', { replace: true });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResend = async () => {
    setError(null);
    setIsResending(true);
    try {
      await auth.requestOtp(phone);
      setSecondsLeft(RESEND_DELAY_SECONDS);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.');
    } finally {
      setIsResending(false);
    }
  };

  return (
    <main className="max-w-md mx-auto px-4 pt-20 pb-28 space-y-6">
      <div className="space-y-2">
        <h1 className="font-bold text-2xl text-primary">Code de vérification</h1>
        <p className="text-sm text-muted-foreground">
          Entrez le code à {CODE_LENGTH} chiffres envoyé au {phone}.
        </p>
        {import.meta.env.DEV && (
          <p className="text-xs text-muted-foreground-soft italic">
            En dev, le code s&apos;affiche dans la console du serveur backend (uvicorn), pas par SMS.
          </p>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <label className="block space-y-1.5">
          <span className="text-xs font-sora font-semibold text-muted-foreground">Code à 6 chiffres</span>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={CODE_LENGTH}
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH))}
            placeholder="123456"
            className="w-full h-14 px-4 rounded-full bg-surface-muted text-center text-2xl tracking-[0.5em] text-foreground outline-none focus:ring-2 focus:ring-primary"
          />
        </label>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full h-14 rounded-full bg-primary text-white font-sora text-sm font-bold hover:opacity-90 active:scale-95 transition-all disabled:opacity-60 disabled:active:scale-100 cursor-pointer"
        >
          {isSubmitting ? 'Vérification...' : 'Valider'}
        </button>
      </form>

      <button
        onClick={handleResend}
        disabled={secondsLeft > 0 || isResending}
        className="w-full text-center text-sm font-sora text-primary disabled:text-muted-foreground-soft cursor-pointer disabled:cursor-not-allowed"
      >
        {secondsLeft > 0 ? `Renvoyer le code (${secondsLeft}s)` : 'Renvoyer le code'}
      </button>
    </main>
  );
};
