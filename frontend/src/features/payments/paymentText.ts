import type { StatusTone } from '../../components/ui/StatusPill';
import type {
  PaymentChannel,
  PaymentOptions,
  PaymentSummary,
  PayoutChannel,
  UserRole,
} from '../../types';
import { isOnlinePaymentActive } from './hooks/usePaymentOptions';

/** Libellés des moyens de paiement et de versement. */
export const CHANNEL_LABELS: Record<PaymentChannel | PayoutChannel, string> = {
  wave: 'Wave',
  orange_money: 'Orange Money',
  free_money: 'Free Money',
  carte: 'Carte bancaire',
  cash: 'Espèces',
  bank: 'Virement bancaire',
};

/**
 * Taux en points de base -> pourcentage français (1 000 -> « 10 % »,
 * 750 -> « 7,5 % »). Aucun calcul de montant ici : seulement l'affichage du
 * taux figé que le serveur a appliqué.
 */
export function formatRate(rateBps: number): string {
  const percent = rateBps / 100;
  const text = Number.isInteger(percent) ? String(percent) : percent.toFixed(2).replace(/0+$/, '');
  return `${text.replace('.', ',')} %`;
}

/** Date courte (« 11 octobre 2026 ») pour les étapes d'un paiement. */
export function formatPaymentDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/**
 * Pastille d'état du paiement, formulée pour CHAQUE partie : le client
 * suit son argent, l'artisan suit ce qu'il va toucher.
 */
export function paymentPill(
  payment: PaymentSummary,
  role: UserRole,
): { label: string; tone: StatusTone } {
  switch (payment.status) {
    case null:
      return role === 'client'
        ? { label: 'À régler', tone: 'warning' }
        : { label: 'Non payé', tone: 'warning' };
    case 'en_attente':
      return { label: 'Paiement en cours', tone: 'warning' };
    case 'retenu':
      return { label: 'Payé · en séquestre', tone: 'info' };
    case 'libere':
      if (role === 'client') return { label: "Versé à l'artisan", tone: 'success' };
      if (payment.payout?.status === 'envoye') return { label: 'Versé', tone: 'success' };
      return { label: 'Versement en cours', tone: 'info' };
    case 'reussi':
      return { label: 'Espèces', tone: 'neutral' };
    case 'echoue':
      return { label: 'Paiement échoué', tone: 'danger' };
    case 'annule':
      return { label: 'Paiement annulé', tone: 'neutral' };
    case 'rembourse':
      return role === 'client'
        ? { label: 'Remboursé', tone: 'success' }
        : { label: 'Remboursé au client', tone: 'neutral' };
  }
}

/** Vrai si le client peut (re)lancer un paiement pour cette intervention. */
export function canStartPayment(payment: PaymentSummary): boolean {
  return (
    payment.status === null ||
    payment.status === 'echoue' ||
    payment.status === 'annule' ||
    payment.status === 'en_attente' ||
    // Espèces déclarées : le client peut encore préférer le paiement sécurisé.
    payment.status === 'reussi'
  );
}

/**
 * Ce que le client doit savoir, selon la configuration RÉELLE : jamais de
 * séquestre promis sans paiement en ligne actif, jamais « bientôt » sans
 * moyen effectivement prévu, jamais « espèces » si elles sont refusées.
 */
export function paymentMethodsText(options: PaymentOptions): string {
  if (isOnlinePaymentActive(options)) {
    return (
      "Payez un devis accepté depuis le suivi de vos travaux. En ligne, Téranga conserve votre argent et ne le verse à l'artisan qu'après votre confirmation de fin des travaux." +
      (options.cashEnabled ? ' Vous pouvez aussi régler en espèces.' : '')
    );
  }
  if (options.cashEnabled) {
    return (
      "Vous réglez l'artisan en espèces, en main propre, une fois les travaux faits." +
      (options.upcomingChannels.length > 0 ? ' Le paiement en ligne sécurisé arrive bientôt.' : '')
    );
  }
  return "Aucun moyen de paiement n'est proposé pour le moment.";
}
