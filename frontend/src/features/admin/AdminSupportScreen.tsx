import React, { useEffect, useState } from 'react';
import { LifeBuoy } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Chip } from '../../components/ui/Chip';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { TextAreaField } from '../../components/ui/Field';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { ApiError, api } from '../../lib/api';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { PageResult } from '../../types/admin';
import type { AdminSupportTicket, SupportTicketStatus } from '../../types';
import { formatDate } from '../interventions/interventionText';
import {
  SUPPORT_CATEGORY_LABELS,
  SUPPORT_REPLY_MIN_LENGTH,
  SUPPORT_STATUS,
} from '../support/supportText';
import { Pager } from './components/Pager';

const ROLE_LABELS: Record<AdminSupportTicket['authorRole'], string> = {
  client: 'Client',
  artisan: 'Artisan',
  admin: 'Admin',
};

const TicketCard: React.FC<{
  ticket: AdminSupportTicket;
  onAnswered: (ticket: AdminSupportTicket) => void;
}> = ({ ticket, onAnswered }) => {
  const [reply, setReply] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isOpen = ticket.status === 'ouvert';
  const status = SUPPORT_STATUS[ticket.status];
  const tooShort = reply.trim().length < SUPPORT_REPLY_MIN_LENGTH;

  const answer = async (resolve: boolean) => {
    if (tooShort) return;
    setError(null);
    setIsSubmitting(true);
    try {
      onAnswered(await api.replySupportTicket(ticket.id, reply.trim(), resolve));
      setReply('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Réponse impossible. Réessayez.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card as="article" padding="lg" className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-foreground">
            {SUPPORT_CATEGORY_LABELS[ticket.category]}
          </p>
          <p className="text-sm text-muted-foreground">
            {ROLE_LABELS[ticket.authorRole]} · {ticket.authorName} · le{' '}
            {formatDate(ticket.createdAt)}
            {ticket.interventionTradeLabel
              ? ` · intervention ${ticket.interventionTradeLabel}`
              : ''}
          </p>
        </div>
        <StatusPill tone={status.tone}>{status.label}</StatusPill>
      </div>
      <p className="rounded-field bg-surface-muted p-3 text-sm text-foreground whitespace-pre-line">
        {ticket.message}
      </p>
      {ticket.adminReply && (
        <p className="text-sm text-muted-foreground">
          <span className="font-semibold text-foreground">Réponse envoyée : </span>
          {ticket.adminReply}
        </p>
      )}
      {isOpen && (
        <div className="space-y-3">
          <TextAreaField
            label="Réponse (visible de l'auteur)"
            value={reply}
            onChange={(event) => setReply(event.target.value)}
            rows={3}
          />
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="brand"
              size="sm"
              isLoading={isSubmitting}
              disabled={tooShort}
              onClick={() => void answer(true)}
            >
              Répondre et clore
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={tooShort || isSubmitting}
              onClick={() => void answer(false)}
            >
              Répondre sans clore
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
};

/**
 * Support (/admin/support) : demandes d'aide des clients et artisans. Les
 * ouvertes d'abord (la plus ancienne en tête) ; chaque réponse est
 * journalisée. Une demande résolue est définitive.
 */
export const AdminSupportScreen: React.FC = () => {
  const [status, setStatus] = useState<SupportTicketStatus>('ouvert');
  const [page, setPage] = useState(1);
  const { data, isLoading, error, run, reload, setData } =
    useAsyncResource<PageResult<AdminSupportTicket>>();

  useEffect(() => {
    run(() => api.listAdminSupportTickets({ status, page }));
  }, [run, status, page]);

  const select = (next: SupportTicketStatus) => {
    setStatus(next);
    setPage(1);
  };

  // Une demande close quitte la file « ouvertes » ; une réponse d'attente
  // y reste, mise à jour.
  const answered = (ticket: AdminSupportTicket) =>
    setData((previous) =>
      previous
        ? {
            ...previous,
            items:
              ticket.status === status
                ? previous.items.map((item) => (item.id === ticket.id ? ticket : item))
                : previous.items.filter((item) => item.id !== ticket.id),
          }
        : previous,
    );

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="font-display text-display-md font-semibold text-primary">Support</h1>
        <p className="text-sm text-muted-foreground">
          Demandes d&apos;aide des clients et des artisans. Les coordonnées sont masquées ; chaque
          réponse est inscrite au journal.
        </p>
      </div>
      <div className="flex gap-2" role="group" aria-label="Filtrer les demandes">
        <Chip selected={status === 'ouvert'} onClick={() => select('ouvert')}>
          Ouvertes
        </Chip>
        <Chip selected={status === 'resolu'} onClick={() => select('resolu')}>
          Résolues
        </Chip>
      </div>

      {isLoading && !data ? (
        <div className="space-y-3" aria-busy="true">
          {[0, 1].map((key) => (
            <Skeleton key={key} className="h-32 rounded-card" />
          ))}
        </div>
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : data && data.items.length === 0 ? (
        <EmptyState
          icon={<LifeBuoy />}
          title={status === 'ouvert' ? 'Aucune demande en attente.' : 'Aucune demande résolue.'}
        />
      ) : data ? (
        <>
          <ul className="space-y-4">
            {data.items.map((ticket) => (
              <li key={ticket.id}>
                <TicketCard ticket={ticket} onAnswered={answered} />
              </li>
            ))}
          </ul>
          <Pager
            page={data.page}
            totalPages={data.totalPages}
            total={data.total}
            onPageChange={setPage}
          />
        </>
      ) : null}
    </div>
  );
};
