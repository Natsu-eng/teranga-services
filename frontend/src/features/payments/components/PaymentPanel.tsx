import React from 'react';
import { ShieldCheck, Wallet } from 'lucide-react';
import { ButtonLink } from '../../../components/ui/Button';
import { StatusPill } from '../../../components/ui/StatusPill';
import { formatFcfa } from '../../../lib/format';
import type { InterventionStatus, PaymentSummary, UserRole } from '../../../types';
import { CHANNEL_LABELS, canStartPayment, formatPaymentDate, paymentPill } from '../paymentText';
import { MoneyBreakdown } from './MoneyBreakdown';

/** Ce que signifie l'état du paiement, en clair, pour la partie qui lit. */
function explanation(payment: PaymentSummary, role: UserRole): string | null {
  const amount = formatFcfa(payment.amountFcfa);
  const net = formatFcfa(payment.netFcfa);
  if (role === 'client') {
    switch (payment.status) {
      case null:
      case 'echoue':
      case 'annule':
        return "Payez en ligne en toute sécurité : Téranga conserve l'argent et ne le verse à l'artisan qu'une fois la fin des travaux confirmée par vous.";
      case 'en_attente':
        return 'Paiement commencé, en attente de confirmation. Vous pouvez le reprendre si vous l’avez interrompu.';
      case 'retenu':
        return `${amount} sont conservés par Téranga (séquestre). Ils seront versés à l'artisan quand vous confirmerez la fin des travaux ; en cas de problème, signalez-le.`;
      case 'libere':
        return payment.releasedAt
          ? `Versé à l'artisan le ${formatPaymentDate(payment.releasedAt)}.`
          : "Versé à l'artisan.";
      case 'reussi':
        return `Vous réglez ${amount} directement à l'artisan, en espèces : ce règlement n'est pas protégé par le séquestre.`;
      case 'rembourse':
        return payment.refundedAt
          ? `${amount} vous ont été remboursés le ${formatPaymentDate(payment.refundedAt)}.`
          : `${amount} vous ont été remboursés.`;
    }
  }
  switch (payment.status) {
    case null:
    case 'echoue':
    case 'annule':
      return "Le client n'a pas encore payé. S'il paie en ligne, l'argent est sécurisé avant les travaux.";
    case 'en_attente':
      return 'Le client est en train de payer.';
    case 'retenu':
      return `Le client a payé : l'argent est en séquestre. Vous recevrez ${net} dès qu'il confirmera la fin des travaux.`;
    case 'libere': {
      const payout = payment.payout;
      if (payout?.status === 'envoye') {
        const date = payout.sentAt ? ` le ${formatPaymentDate(payout.sentAt)}` : '';
        return `${formatFcfa(payout.amountFcfa)} versés${date} sur ${CHANNEL_LABELS[payout.channel]}.`;
      }
      const destination = payout ? ` vers votre compte ${CHANNEL_LABELS[payout.channel]}` : '';
      return payout?.status === 'echoue'
        ? `Versement de ${net} retardé${destination} : Téranga le relance, rien n'est perdu.`
        : `Versement de ${net} en cours${destination}.`;
    }
    case 'reussi':
      return `Paiement en espèces : vous encaissez ${amount} directement. Commission due à Téranga : ${formatFcfa(payment.commission.amountFcfa)}.`;
    case 'rembourse':
      return 'Le client a été remboursé : aucune commission ne vous est prélevée.';
  }
}

interface PaymentPanelProps {
  interventionId: string;
  interventionStatus: InterventionStatus;
  payment: PaymentSummary;
  role: UserRole;
}

/**
 * Volet « Paiement » d'une intervention (carte du client et de l'artisan) :
 * état daté, montants selon la partie, et l'action utile (payer, reprendre).
 */
export const PaymentPanel: React.FC<PaymentPanelProps> = ({
  interventionId,
  interventionStatus,
  payment,
  role,
}) => {
  const pill = paymentPill(payment, role);
  const text = explanation(payment, role);
  const showPay =
    role === 'client' && interventionStatus === 'en_cours' && canStartPayment(payment);
  const isSecured = payment.status === 'retenu';

  return (
    <section aria-label="Paiement" className="rounded-field bg-surface-muted p-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary">
          {isSecured ? (
            <ShieldCheck aria-hidden className="w-4 h-4" />
          ) : (
            <Wallet aria-hidden className="w-4 h-4" />
          )}
          Paiement
          {payment.channel && (
            <span className="font-normal text-muted-foreground">
              · {CHANNEL_LABELS[payment.channel]}
            </span>
          )}
        </p>
        <StatusPill tone={pill.tone}>{pill.label}</StatusPill>
      </div>

      <MoneyBreakdown payment={payment} role={role} />

      {text && <p className="text-sm text-muted-foreground">{text}</p>}

      {showPay && (
        <ButtonLink
          to={`/paiement/${interventionId}`}
          variant="primary"
          fullWidth
          leadingIcon={<ShieldCheck aria-hidden className="w-5 h-5" />}
        >
          {payment.status === 'en_attente'
            ? 'Reprendre le paiement'
            : payment.status === 'reussi'
              ? 'Payer en ligne plutôt'
              : `Payer ${formatFcfa(payment.amountFcfa)}`}
        </ButtonLink>
      )}
    </section>
  );
};
