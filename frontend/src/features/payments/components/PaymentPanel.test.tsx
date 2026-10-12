import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { PaymentPanel } from './PaymentPanel';
import { paymentFixture } from '../paymentFixtures';
import type { InterventionStatus, PaymentSummary, UserRole } from '../../../types';

function renderPanel(
  payment: PaymentSummary,
  role: UserRole,
  interventionStatus: InterventionStatus = 'en_cours',
) {
  return render(
    <MemoryRouter>
      <PaymentPanel
        interventionId="int-1"
        interventionStatus={interventionStatus}
        payment={payment}
        role={role}
      />
    </MemoryRouter>,
  );
}

function panel() {
  return screen.getByRole('region', { name: 'Paiement' });
}

describe('PaymentPanel — transparence des montants selon la partie', () => {
  afterEach(cleanup);

  it('montre au client ce qu’il paie, sans frais cachés ni « part artisan » ambiguë', () => {
    renderPanel(paymentFixture(), 'client');

    const region = panel();
    expect(within(region).getByText('Total à payer')).toBeInTheDocument();
    expect(within(region).getByText('12 000 FCFA')).toBeInTheDocument();
    expect(within(region).getByText(/Aucun frais ajouté pour vous/)).toBeInTheDocument();
    expect(within(region).queryByText('Vous recevez')).not.toBeInTheDocument();
    expect(within(region).getByRole('link', { name: 'Payer 12 000 FCFA' })).toHaveAttribute(
      'href',
      '/paiement/int-1',
    );
  });

  it("montre à l'artisan le prix, la commission prélevée (taux figé) et son net", () => {
    renderPanel(
      paymentFixture({ commission: { rateBps: 1000, amountFcfa: 1_200, status: 'due' } }),
      'artisan',
    );

    const region = panel();
    expect(within(region).getByText('Prix du devis (payé par le client)')).toBeInTheDocument();
    expect(within(region).getByText('Commission Téranga (10 %)')).toBeInTheDocument();
    expect(within(region).getByText('− 1 200 FCFA')).toBeInTheDocument();
    expect(within(region).getByText('Vous recevez')).toBeInTheDocument();
    expect(within(region).getByText('10 800 FCFA')).toBeInTheDocument();
    // L'artisan ne paie rien : aucune action de paiement.
    expect(within(region).queryByRole('link')).not.toBeInTheDocument();
  });

  it('signale une commission encore estimée (avant tout paiement)', () => {
    renderPanel(paymentFixture(), 'artisan');

    expect(within(panel()).getByText('Commission Téranga (10 %), estimée')).toBeInTheDocument();
  });

  it('formate un taux non entier (7,5 %)', () => {
    renderPanel(
      paymentFixture({
        commission: { rateBps: 750, amountFcfa: 900, status: 'due' },
        netFcfa: 11_100,
      }),
      'artisan',
    );

    expect(within(panel()).getByText('Commission Téranga (7,5 %)')).toBeInTheDocument();
  });

  it('explique le séquestre aux deux parties', () => {
    const held = paymentFixture({ status: 'retenu', channel: 'wave' });

    renderPanel(held, 'client');
    expect(within(panel()).getByText('Payé · en séquestre')).toBeInTheDocument();
    expect(within(panel()).getByText(/conservés par Téranga \(séquestre\)/)).toBeInTheDocument();
    expect(within(panel()).queryByRole('link')).not.toBeInTheDocument();
    cleanup();

    renderPanel(held, 'artisan');
    expect(
      within(panel()).getByText(/Vous recevrez 10 800 FCFA dès qu'il confirmera/),
    ).toBeInTheDocument();
  });

  it("annonce à l'artisan le versement reçu, avec la date et le moyen", () => {
    renderPanel(
      paymentFixture({
        status: 'libere',
        channel: 'wave',
        commission: { rateBps: 1000, amountFcfa: 1_200, status: 'collectee' },
        payout: {
          status: 'envoye',
          amountFcfa: 10_800,
          channel: 'orange_money',
          sentAt: '2026-10-11T10:00:00Z',
        },
      }),
      'artisan',
      'terminee',
    );

    expect(within(panel()).getByText('Versé')).toBeInTheDocument();
    expect(
      within(panel()).getByText(/10 800 FCFA versés le 11 octobre 2026 sur Orange Money/),
    ).toBeInTheDocument();
  });

  it("dit à l'artisan payé en espèces la commission qu'il doit", () => {
    renderPanel(
      paymentFixture({
        status: 'reussi',
        channel: 'cash',
        commission: { rateBps: 1000, amountFcfa: 1_200, status: 'due' },
      }),
      'artisan',
    );

    expect(within(panel()).getByText(/vous encaissez 12 000 FCFA directement/)).toBeInTheDocument();
    expect(within(panel()).getByText(/Commission due à Téranga : 1 200 FCFA/)).toBeInTheDocument();
  });

  it('confirme le remboursement au client', () => {
    renderPanel(
      paymentFixture({ status: 'rembourse', channel: 'wave', refundedAt: '2026-10-11T10:00:00Z' }),
      'client',
      'annulee',
    );

    expect(within(panel()).getByText('Remboursé')).toBeInTheDocument();
    expect(within(panel()).getByText(/remboursés le 11 octobre 2026/)).toBeInTheDocument();
  });

  it('propose de reprendre un paiement commencé', () => {
    renderPanel(
      paymentFixture({ status: 'en_attente', channel: 'wave', checkoutUrl: 'https://x/checkout' }),
      'client',
    );

    expect(
      within(panel()).getByRole('link', { name: 'Reprendre le paiement' }),
    ).toBeInTheDocument();
  });

  it('espèces seulement : propose de déclarer le cash, jamais de payer en ligne', () => {
    renderPanel(paymentFixture({ onlineAvailable: false }), 'client');

    expect(
      within(panel()).getByRole('link', { name: 'Déclarer le paiement en espèces' }),
    ).toHaveAttribute('href', '/paiement/int-1');
    expect(within(panel()).queryByText(/en ligne en toute sécurité/)).not.toBeInTheDocument();
  });

  it('espèces seulement : après le cash déclaré, aucune option « payer en ligne » morte', () => {
    renderPanel(
      paymentFixture({ status: 'reussi', channel: 'cash', onlineAvailable: false }),
      'client',
    );

    expect(within(panel()).queryByRole('link')).not.toBeInTheDocument();
    expect(within(panel()).queryByText(/séquestre/)).not.toBeInTheDocument();
  });

  it("espèces seulement : l'artisan sait qu'il sera réglé en main propre", () => {
    renderPanel(paymentFixture({ onlineAvailable: false }), 'artisan');

    expect(within(panel()).getByText(/vous réglera en espèces/)).toBeInTheDocument();
  });
});
