import { describe, expect, it } from 'vitest';
import { paymentFixture } from '../payments/paymentFixtures';
import {
  adminOutcomeLabels,
  adminOutcomePill,
  disputeFormNotice,
  disputeOutcomeText,
  disputePendingNotice,
  isFundsHeld,
} from './disputeText';

const held = paymentFixture({ status: 'retenu', channel: 'wave' });
const cash = paymentFixture({ status: 'reussi', channel: 'cash' });

describe('libellés de litige, fidèles à l’argent réellement détenu', () => {
  it('seul un paiement en ligne retenu est « gelé »', () => {
    expect(isFundsHeld(held)).toBe(true);
    expect(isFundsHeld(cash)).toBe(false);
    expect(isFundsHeld(null)).toBe(false);
    expect(disputePendingNotice(held)).toMatch(/L'argent est gelé/);
    expect(disputePendingNotice(cash)).not.toMatch(/gelé/);
    expect(disputeFormNotice(cash)).not.toMatch(/gelé/);
    expect(disputeFormNotice(null)).not.toMatch(/espèces/);
  });

  it('« remboursé » et « versé » seulement quand c’est vrai', () => {
    expect(disputeOutcomeText('rembourse', paymentFixture({ status: 'rembourse' }))).toMatch(
      /le client a été remboursé/,
    );
    expect(disputeOutcomeText('rembourse', cash)).not.toMatch(/remboursé/);
    expect(disputeOutcomeText('libere', paymentFixture({ status: 'libere' }))).toMatch(/versé/);
    expect(disputeOutcomeText('libere', cash)).toBe('Litige clos par Téranga : travaux reconnus.');
  });

  it('le back-office annonce une médiation quand Téranga ne détient rien', () => {
    expect(adminOutcomeLabels(held).rembourse.action).toBe('Rembourser le client');
    expect(adminOutcomeLabels(cash).rembourse.action).toBe('Clore en faveur du client');
    expect(adminOutcomeLabels(null).libere.effect).toMatch(/commission reste due/);
    expect(adminOutcomePill('rembourse', cash)).toBe('Clos en faveur du client');
    expect(adminOutcomePill('rembourse', paymentFixture({ status: 'rembourse' }))).toBe(
      'Client remboursé',
    );
  });
});
