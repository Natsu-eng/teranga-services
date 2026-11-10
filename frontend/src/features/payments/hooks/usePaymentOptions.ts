import { useEffect } from 'react';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';
import type { PaymentOptions } from '../../../types';

/**
 * Moyens de paiement RÉELLEMENT disponibles (GET /payments/options), lus
 * par le client (profil, historique) et l'artisan (gains). Seule source de
 * vérité : rien n'est supposé côté front (mode espèces, paiement en ligne
 * actif ou « bientôt »).
 */
export function usePaymentOptions() {
  const { data, isLoading, error, run, reload } = useAsyncResource<PaymentOptions>();

  useEffect(() => {
    run(() => api.getPaymentOptions());
  }, [run]);

  return { data, isLoading, error, reload };
}

/** Vrai si le paiement en ligne (avec séquestre) est actif sur l'instance. */
export function isOnlinePaymentActive(options: PaymentOptions): boolean {
  return options.onlineChannels.length > 0;
}
