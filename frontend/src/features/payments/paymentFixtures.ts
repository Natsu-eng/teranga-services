/**
 * Jeux de données des TESTS de paiement (jamais importés par le code de
 * production). Montants cohérents : 12 000 FCFA, 10 %, net 10 800.
 */
import type { Intervention, PaymentSummary, ServiceRequest } from '../../types';

export const serviceRequestFixture: ServiceRequest = {
  id: 'req-1',
  tradeCode: 'plomberie',
  tradeLabel: 'Plomberie',
  description: 'Fuite sous l’évier.',
  photoUrl: null,
  location: { lat: 14.6937, lng: -17.4441 },
  locationLabel: null,
  urgency: 'normal',
  aiEstimateMinFcfa: null,
  aiEstimateMaxFcfa: null,
  status: 'en_relation',
  expiresAt: null,
  createdAt: '2026-10-01T00:00:00Z',
};

export function paymentFixture(overrides: Partial<PaymentSummary> = {}): PaymentSummary {
  return {
    amountFcfa: 12_000,
    commission: { rateBps: 1000, amountFcfa: 1_200, status: null },
    netFcfa: 10_800,
    status: null,
    channel: null,
    checkoutUrl: null,
    checkoutExpiresAt: null,
    paidAt: null,
    releasedAt: null,
    refundedAt: null,
    payout: null,
    onlineAvailable: true,
    ...overrides,
  };
}

export function payableInterventionFixture(overrides: Partial<Intervention> = {}): Intervention {
  return {
    id: 'int-1',
    serviceRequest: serviceRequestFixture,
    clientId: 'client-1',
    artisanId: 'artisan-1',
    status: 'en_cours',
    commissionRateBps: 1000,
    agreedAmountFcfa: 12_000,
    scheduledAt: null,
    completedAt: null,
    cancellation: null,
    quote: {
      id: 'q-1',
      laborFcfa: 8_000,
      materialsFcfa: 4_000,
      totalFcfa: 12_000,
      status: 'accepte',
      createdAt: '2026-10-02T00:00:00Z',
    },
    review: null,
    conversationId: null,
    payment: paymentFixture(),
    dispute: null,
    createdAt: '2026-10-01T00:00:00Z',
    ...overrides,
  };
}
