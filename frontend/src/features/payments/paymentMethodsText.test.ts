import { describe, expect, it } from 'vitest';
import type { PaymentOptions } from '../../types';
import { paymentMethodsText } from './paymentText';

/**
 * Le texte des moyens de paiement ne promet jamais plus que la
 * configuration réelle (GET /payments/options).
 */
function options(overrides: Partial<PaymentOptions>): PaymentOptions {
  return {
    onlineChannels: [],
    upcomingChannels: [],
    cashEnabled: true,
    currency: 'XOF',
    ...overrides,
  };
}

describe('paymentMethodsText', () => {
  it('paiement en ligne actif : séquestre décrit, espèces mentionnées si acceptées', () => {
    const text = paymentMethodsText(options({ onlineChannels: ['wave'] }));
    expect(text).toMatch(/Téranga conserve votre argent/);
    expect(text).toMatch(/Vous pouvez aussi régler en espèces/);
    expect(
      paymentMethodsText(options({ onlineChannels: ['wave'], cashEnabled: false })),
    ).not.toMatch(/espèces/);
  });

  it('espèces seules : aucun séquestre promis ; « bientôt » seulement si des moyens sont prévus', () => {
    const planned = paymentMethodsText(options({ upcomingChannels: ['wave', 'carte'] }));
    expect(planned).toMatch(/Vous réglez l'artisan en espèces/);
    expect(planned).toMatch(/arrive bientôt/);
    expect(planned).not.toMatch(/conserve/);

    const nothingPlanned = paymentMethodsText(options({}));
    expect(nothingPlanned).not.toMatch(/bientôt/);
  });

  it('aucun moyen proposé : le dit, sans rien inventer', () => {
    expect(paymentMethodsText(options({ cashEnabled: false }))).toBe(
      "Aucun moyen de paiement n'est proposé pour le moment.",
    );
  });
});
