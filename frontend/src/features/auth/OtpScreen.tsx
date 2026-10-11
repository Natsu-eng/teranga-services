import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, type Location } from 'react-router';
import { ApiError } from '../../lib/api';
import type { AuthIntent, SignupRole } from '../../lib/api/auth-client';
import { Button } from '../../components/ui/Button';
import { TextField } from '../../components/ui/Field';
import { AuthShell } from './components/AuthShell';
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
      setError(
        err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
      );
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
      setError(
        err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
      );
    } finally {
      setIsResending(false);
    }
  };

  return (
    <AuthShell
      title="Code de vérification"
      description={
        <>
          Entrez le code à {CODE_LENGTH} chiffres envoyé au{' '}
          <span className="font-semibold text-foreground whitespace-nowrap">{phone}</span>.
        </>
      }
      // Retour à la saisie du numéro, en conservant tout le contexte du parcours.
      onBack={() => navigate('/connexion/telephone', { state: { ...state, phone: undefined } })}
    >
      <form onSubmit={handleSubmit} className="flex-1 flex flex-col gap-6" noValidate>
        <TextField
          label="Code à 6 chiffres"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={CODE_LENGTH}
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH))}
          placeholder="123456"
          inputClassName="h-16 text-center font-display text-display-md tracking-[0.4em]"
          hint={
            import.meta.env.DEV
              ? "En dev, le code s'affiche dans la console du serveur backend (uvicorn), pas par SMS."
              : undefined
          }
          error={error}
        />

        <div className="mt-auto space-y-3">
          <Button type="submit" variant="brand" size="lg" fullWidth isLoading={isSubmitting}>
            {isSubmitting ? 'Vérification...' : 'Valider'}
          </Button>
          <Button
            variant="ghost"
            fullWidth
            onClick={handleResend}
            disabled={secondsLeft > 0 || isResending}
          >
            {secondsLeft > 0 ? `Renvoyer le code (${secondsLeft}s)` : 'Renvoyer le code'}
          </Button>
        </div>
      </form>
    </AuthShell>
  );
};
