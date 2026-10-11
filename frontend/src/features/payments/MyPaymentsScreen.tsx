import React, { useEffect } from 'react';
import { Receipt } from 'lucide-react';
import { Link } from 'react-router';
import { AppBar } from '../../components/ui/AppBar';
import { ButtonLink } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill, type StatusTone } from '../../components/ui/StatusPill';
import { cardClasses } from '../../components/ui/styles';
import { api } from '../../lib/api';
import { formatFcfa } from '../../lib/format';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { ClientPayment, PaymentStatus } from '../../types';
import { CHANNEL_LABELS, formatPaymentDate } from './paymentText';

const STATUS: Record<PaymentStatus, { label: string; tone: StatusTone }> = {
  en_attente: { label: 'En attente', tone: 'warning' },
  retenu: { label: 'En séquestre', tone: 'info' },
  libere: { label: "Versé à l'artisan", tone: 'success' },
  reussi: { label: 'Espèces', tone: 'neutral' },
  echoue: { label: 'Échoué', tone: 'danger' },
  annule: { label: 'Annulé', tone: 'neutral' },
  rembourse: { label: 'Remboursé', tone: 'success' },
};

/** La date qui compte pour ce paiement, en clair. */
function lastStep(payment: ClientPayment): string {
  if (payment.refundedAt) return `Remboursé le ${formatPaymentDate(payment.refundedAt)}`;
  if (payment.releasedAt) return `Versé le ${formatPaymentDate(payment.releasedAt)}`;
  if (payment.paidAt) return `Payé le ${formatPaymentDate(payment.paidAt)}`;
  return `Commencé le ${formatPaymentDate(payment.createdAt)}`;
}

/**
 * Historique des paiements du client (/mes-paiements). Chaque ligne mène
 * au suivi de l'intervention concernée.
 */
export const MyPaymentsScreen: React.FC = () => {
  const { data, isLoading, error, run, reload } = useAsyncResource<ClientPayment[]>();

  useEffect(() => {
    run(() => api.listMyPayments());
  }, [run]);

  return (
    <>
      <AppBar title="Mes paiements" backTo="/profil" />
      <main className="w-full max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-10 space-y-4">
        <p className="text-sm text-muted-foreground">
          Vos paiements en ligne sont conservés par Téranga jusqu&apos;à votre confirmation de fin
          des travaux, puis versés à l&apos;artisan. Aucun frais ne s&apos;ajoute au prix du devis.
        </p>
        {isLoading && !data ? (
          <div className="space-y-3" aria-busy="true">
            {[0, 1, 2].map((key) => (
              <Skeleton key={key} className="h-20 rounded-card" />
            ))}
          </div>
        ) : error && !data ? (
          <ErrorState message={error.message} onRetry={reload} />
        ) : data && data.length === 0 ? (
          <EmptyState
            icon={<Receipt />}
            title="Aucun paiement pour le moment."
            description="Après avoir accepté un devis, vous pourrez le régler depuis le suivi de vos travaux."
          >
            <ButtonLink to="/mes-interventions" variant="outline" size="sm">
              Voir mes devis et travaux
            </ButtonLink>
          </EmptyState>
        ) : (
          <ul className="space-y-3">
            {(data ?? []).map((payment) => {
              const status = STATUS[payment.status];
              return (
                <li key={payment.id}>
                  <Link
                    to="/mes-interventions"
                    className={cardClasses({ interactive: true, className: 'block space-y-1' })}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold text-foreground">
                        {payment.tradeLabel} · {payment.artisanName}
                      </p>
                      <StatusPill tone={status.tone}>{status.label}</StatusPill>
                    </div>
                    <p className="font-display text-title font-semibold text-primary">
                      {formatFcfa(payment.amountFcfa)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {CHANNEL_LABELS[payment.channel]} · {lastStep(payment)}
                    </p>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </>
  );
};
