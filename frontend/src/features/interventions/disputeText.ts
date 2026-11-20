import type { Dispute, PaymentSummary } from '../../types';

/**
 * Libellés d'un litige, DÉRIVÉS DE L'ÉTAT RÉEL DU PAIEMENT. Le serveur
 * stocke l'issue `libere` (en faveur de l'artisan) ou `rembourse` (en faveur
 * du client), mais l'effet dépend de l'argent que Téranga détient vraiment :
 *
 * - paiement en ligne retenu (séquestre) : versement à l'artisan ou
 *   remboursement réel du client ;
 * - espèces, ou règlement hors plateforme : Téranga ne détient rien. Le litige
 *   est une MÉDIATION : jamais de « remboursement » ni d'« argent gelé »
 *   annoncés, puisque Téranga ne peut ni l'un ni l'autre.
 *
 * Seule source de ces textes : la carte d'intervention, le texte de clôture
 * et le back-office les partagent (aucun écart possible entre écrans).
 */

type Outcome = NonNullable<Dispute['outcome']>;

/** Vrai seulement si Téranga détient réellement l'argent (séquestre en ligne). */
export function isFundsHeld(payment: PaymentSummary | null): boolean {
  return payment?.status === 'retenu';
}

function isCash(payment: PaymentSummary | null): boolean {
  return payment?.channel === 'cash';
}

/** Ce que Téranga ne peut pas faire, dit une fois, sans détour. */
const CASH_NOT_HELD =
  'Téranga ne détient pas les paiements en espèces et ne peut pas les rembourser : un éventuel remboursement se règle entre vous.';

/** Avant d'envoyer un signalement : ce qui va se passer, honnêtement. */
export function disputeFormNotice(payment: PaymentSummary | null): string {
  if (isFundsHeld(payment)) {
    return "L'argent reste gelé jusqu'à la décision d'un conseiller Téranga. Expliquez la situation.";
  }
  return isCash(payment)
    ? `Un conseiller Téranga examinera la situation et vous aidera à trouver une issue. ${CASH_NOT_HELD}`
    : 'Un conseiller Téranga examinera la situation et vous aidera à trouver une issue. Expliquez la situation.';
}

/** Pendant le litige : où en est l'argent, et qui décide. */
export function disputePendingNotice(payment: PaymentSummary | null): string {
  if (isFundsHeld(payment)) {
    return "L'argent est gelé : un conseiller Téranga examine la situation et tranchera (versement à l'artisan ou remboursement du client).";
  }
  return isCash(payment)
    ? `Un conseiller Téranga examine la situation (médiation). ${CASH_NOT_HELD}`
    : 'Un conseiller Téranga examine la situation (médiation).';
}

/** Une fois tranché : ce qui a réellement été fait. */
export function disputeOutcomeText(outcome: Outcome, payment: PaymentSummary | null): string {
  if (outcome === 'libere') {
    return payment?.status === 'libere'
      ? "Litige tranché par Téranga : paiement versé à l'artisan."
      : 'Litige clos par Téranga : travaux reconnus.';
  }
  if (payment?.status === 'rembourse') {
    return 'Litige tranché par Téranga : le client a été remboursé, aucune commission prélevée.';
  }
  return isCash(payment)
    ? `Litige clos par Téranga en faveur du client : aucune commission n'est due. ${CASH_NOT_HELD}`
    : "Litige clos par Téranga en faveur du client : aucune commission n'est due.";
}

/** Back-office : bouton et effet annoncé de chaque issue, selon l'argent détenu. */
export function adminOutcomeLabels(
  payment: PaymentSummary | null,
): Record<Outcome, { action: string; effect: string }> {
  if (isFundsHeld(payment)) {
    return {
      libere: {
        action: "Verser à l'artisan",
        effect:
          "L'intervention est close comme terminée ; l'artisan reçoit son net, la commission est prélevée.",
      },
      rembourse: {
        action: 'Rembourser le client',
        effect:
          "L'intervention est annulée ; le client est intégralement remboursé, aucune commission.",
      },
    };
  }
  return {
    libere: {
      action: 'Clore : travaux reconnus',
      effect:
        "L'intervention est close comme terminée ; la commission reste due par l'artisan. Aucun mouvement d'argent par Téranga.",
    },
    rembourse: {
      action: 'Clore en faveur du client',
      effect:
        "L'intervention est annulée et la commission annulée. Téranga ne détient pas ce paiement : aucun remboursement n'est effectué par Téranga.",
    },
  };
}

/**
 * Back-office : commission qui n'est PLUS due (déjà prélevée ou annulée).
 * Une décision « en faveur du client » est alors refusée par le serveur
 * (rien n'est modifié) : l'admin le voit avant même de cliquer.
 */
export function settledCommissionWarning(payment: PaymentSummary | null): string | null {
  const status = payment?.commission.status;
  if (status === 'collectee') {
    return 'Commission déjà prélevée : une décision en faveur du client sera refusée, à traiter manuellement.';
  }
  if (status === 'annulee') {
    return 'Commission déjà annulée : une décision en faveur du client sera refusée, à traiter manuellement.';
  }
  return null;
}

/** Back-office : pastille d'un litige tranché, fidèle à ce qui a été fait. */
export function adminOutcomePill(outcome: Outcome, payment: PaymentSummary | null): string {
  if (outcome === 'libere') {
    return payment?.status === 'libere' ? 'Versé à l’artisan' : 'Clos : travaux reconnus';
  }
  return payment?.status === 'rembourse' ? 'Client remboursé' : 'Clos en faveur du client';
}
