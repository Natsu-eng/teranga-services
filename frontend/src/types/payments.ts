/**
 * Paiement, gains de l'artisan et versements.
 */
import type { InterventionStatus } from './interventions';

/*
 * Paiements (BUILD_PLAN.md §3.5). Montants en FCFA ENTIERS, taux en points
 * de base (1 000 = 10 %) : le front n'en calcule aucun, il affiche ceux du
 * serveur.
 */
export type PaymentChannel = 'wave' | 'orange_money' | 'free_money' | 'carte' | 'cash';

/**
 * En ligne (séquestre) : en_attente -> retenu -> libere | rembourse ;
 * checkout abandonné : echoue | annule. Espèces : reussi (réglé
 * directement à l'artisan) ou annule.
 */
export type PaymentStatus =
  'en_attente' | 'retenu' | 'libere' | 'reussi' | 'echoue' | 'annule' | 'rembourse';

export type PlatformFeeStatus = 'due' | 'collectee' | 'annulee';
export type PayoutChannel = 'wave' | 'orange_money' | 'bank';
export type PayoutStatus = 'en_attente' | 'envoye' | 'echoue';

export interface PaymentSummary {
  /** Prix du devis accepté : ce que paie le client, sans frais ajoutés. */
  amountFcfa: number;
  commission: {
    rateBps: number;
    amountFcfa: number;
    /** `null` : pas encore enregistrée (estimation sur le taux figé). */
    status: PlatformFeeStatus | null;
  };
  /** Ce que touche l'artisan : montant − commission. */
  netFcfa: number;
  /** `null` : aucun paiement initié. */
  status: PaymentStatus | null;
  channel: PaymentChannel | null;
  checkoutUrl: string | null;
  checkoutExpiresAt: string | null;
  paidAt: string | null;
  releasedAt: string | null;
  refundedAt: string | null;
  payout: {
    status: PayoutStatus;
    amountFcfa: number;
    channel: PayoutChannel;
    sentAt: string | null;
  } | null;
  /**
   * Le paiement en ligne (séquestre) est-il proposé ? Faux au lancement
   * « espèces seulement » : l'interface ne promet alors ni séquestre ni
   * « payer en ligne », seulement le règlement en espèces.
   */
  onlineAvailable: boolean;
}

/** Moyens de paiement réellement proposés par le serveur. */
export interface PaymentOptions {
  onlineChannels: PaymentChannel[];
  cashEnabled: boolean;
  currency: string;
}

/** Un paiement dans l'historique du client. */
export interface ClientPayment {
  id: string;
  interventionId: string;
  tradeLabel: string;
  artisanName: string;
  amountFcfa: number;
  channel: PaymentChannel;
  status: PaymentStatus;
  createdAt: string;
  paidAt: string | null;
  releasedAt: string | null;
  refundedAt: string | null;
}

export interface EarningsTotals {
  paidOutFcfa: number;
  payoutPendingFcfa: number;
  inEscrowFcfa: number;
  commissionCollectedFcfa: number;
  cashReceivedFcfa: number;
  commissionDueFcfa: number;
}

export interface EarningItem {
  interventionId: string;
  tradeLabel: string;
  clientName: string;
  interventionStatus: InterventionStatus;
  payment: PaymentSummary;
}

export interface ArtisanEarnings {
  totals: EarningsTotals;
  items: EarningItem[];
}

/** Où l'artisan reçoit ses versements : toujours le numéro vérifié du compte. */
export interface PayoutSettings {
  channel: PayoutChannel;
  chosen: boolean;
  allowedChannels: PayoutChannel[];
  destinationPhone: string;
}
