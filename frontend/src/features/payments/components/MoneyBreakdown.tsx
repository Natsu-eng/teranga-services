import React from 'react';
import { formatFcfa } from '../../../lib/format';
import type { PaymentSummary, UserRole } from '../../../types';
import { formatRate } from '../paymentText';

interface MoneyBreakdownProps {
  payment: PaymentSummary;
  role: UserRole;
}

/**
 * Les montants d'une intervention, sans ambiguïté, selon la partie :
 *
 * - client : ce qu'il paie (le prix du devis), et la mention explicite
 *   qu'aucun frais ne s'y ajoute — la commission est prise sur la part de
 *   l'artisan ;
 * - artisan : le prix du devis, la commission de Téranga (taux figé et
 *   montant) et ce qu'il touche réellement.
 *
 * Tous les montants viennent du serveur ; rien n'est recalculé ici.
 */
export const MoneyBreakdown: React.FC<MoneyBreakdownProps> = ({ payment, role }) => {
  const rate = formatRate(payment.commission.rateBps);

  if (role === 'client') {
    return (
      <div className="space-y-1">
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 text-sm">
          <dt className="font-semibold text-foreground">Total à payer</dt>
          <dd className="text-right font-display text-title font-semibold text-primary">
            {formatFcfa(payment.amountFcfa)}
          </dd>
        </dl>
        <p className="text-xs text-muted-foreground">
          Aucun frais ajouté pour vous : la commission de Téranga ({rate}) est prélevée sur la part
          de l&apos;artisan.
        </p>
      </div>
    );
  }

  const estimated = payment.commission.status === null;
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
      <dt className="text-muted-foreground">Prix du devis (payé par le client)</dt>
      <dd className="text-right text-foreground">{formatFcfa(payment.amountFcfa)}</dd>
      <dt className="text-muted-foreground">
        Commission Téranga ({rate}){estimated ? ', estimée' : ''}
      </dt>
      <dd className="text-right text-foreground">− {formatFcfa(payment.commission.amountFcfa)}</dd>
      <dt className="font-semibold text-foreground">Vous recevez</dt>
      <dd className="text-right font-display text-title font-semibold text-primary">
        {formatFcfa(payment.netFcfa)}
      </dd>
    </dl>
  );
};
