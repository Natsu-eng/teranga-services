/**
 * Interventions : statuts, devis, annulation, litige.
 */
import type { Review } from './artisans';
import type { PaymentSummary } from './payments';
import type { ServiceRequest } from './requests';
import type { UserRole } from './users';

export type InterventionStatus =
  'proposee' | 'acceptee' | 'en_cours' | 'terminee' | 'annulee' | 'litige';

export type QuoteStatus = 'propose' | 'accepte' | 'refuse' | 'expire';

export interface Quote {
  id: string;
  laborFcfa: number;
  materialsFcfa: number;
  totalFcfa: number;
  status: QuoteStatus;
  createdAt: string;
}

export type CancellationKind = 'refus' | 'annulation' | 'arbitrage';

export interface Cancellation {
  kind: CancellationKind;
  by: UserRole | 'admin';
  reason: string | null;
  at: string;
}

export interface Dispute {
  openedBy: UserRole | 'admin';
  reason: string;
  openedAt: string;
  outcome: 'libere' | 'rembourse' | null;
  resolvedAt: string | null;
  resolutionNote: string | null;
}

export interface Intervention {
  id: string;
  serviceRequest: ServiceRequest;
  clientId: string;
  artisanId: string;
  status: InterventionStatus;
  commissionRateBps: number;
  agreedAmountFcfa: number | null;
  scheduledAt: string | null;
  completedAt: string | null;
  /** Comment une intervention `annulee` a été close (refus, annulation, arbitrage). */
  cancellation: Cancellation | null;
  quote: Quote | null;
  review: Review | null;
  /** Fil de discussion client ↔ artisan, ouvert avec l'intervention (messagerie). */
  conversationId: string | null;
  /** Volet financier, dès qu'un devis est accepté (deux parties et admin seulement). */
  payment: PaymentSummary | null;
  dispute: Dispute | null;
  createdAt: string;
}
