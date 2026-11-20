import React, { useEffect, useState } from 'react';
import { LifeBuoy, ShieldCheck } from 'lucide-react';
import { useSearchParams } from 'react-router';
import { AppBar } from '../../components/ui/AppBar';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SelectField, TextAreaField } from '../../components/ui/Field';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { ApiError, api } from '../../lib/api';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { SupportCategory, SupportTicket } from '../../types';
import { formatDate } from '../interventions/interventionText';
import {
  SUPPORT_CATEGORIES,
  SUPPORT_CATEGORY_LABELS,
  SUPPORT_MESSAGE_MAX_LENGTH,
  SUPPORT_MESSAGE_MIN_LENGTH,
  SUPPORT_STATUS,
  interventionIdFromQuery,
} from './supportText';

const TicketItem: React.FC<{ ticket: SupportTicket }> = ({ ticket }) => {
  const status = SUPPORT_STATUS[ticket.status];
  return (
    <Card as="li" className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-foreground">
            {SUPPORT_CATEGORY_LABELS[ticket.category]}
          </p>
          <p className="text-caption text-muted-foreground">
            Envoyée le {formatDate(ticket.createdAt)}
            {ticket.interventionTradeLabel ? ` · ${ticket.interventionTradeLabel}` : ''}
          </p>
        </div>
        <StatusPill tone={status.tone}>{status.label}</StatusPill>
      </div>
      <p className="text-sm text-muted-foreground whitespace-pre-line">{ticket.message}</p>
      {ticket.adminReply && (
        <div className="rounded-field bg-emerald-tint p-3 text-sm">
          <p className="font-semibold text-primary">Réponse de Téranga</p>
          <p className="text-foreground whitespace-pre-line">{ticket.adminReply}</p>
        </div>
      )}
    </Card>
  );
};

/**
 * Aide (/aide) : écrire à Téranga et suivre ses demandes. Client et
 * artisan. Une intervention peut être pré-remplie depuis la carte
 * d'intervention (`?intervention=<id>`) : le serveur vérifie qu'elle
 * appartient bien à l'utilisateur.
 */
export const SupportScreen: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [interventionId, setInterventionId] = useState(() =>
    interventionIdFromQuery(searchParams.get('intervention')),
  );
  const [category, setCategory] = useState<SupportCategory | ''>(
    interventionId ? 'utilisateur' : '',
  );
  const [message, setMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const {
    data: tickets,
    isLoading,
    error,
    run,
    reload,
    setData,
  } = useAsyncResource<SupportTicket[]>();

  useEffect(() => {
    run(() => api.listMySupportTickets());
  }, [run]);

  const trimmed = message.trim();
  const canSend =
    category !== '' &&
    trimmed.length >= SUPPORT_MESSAGE_MIN_LENGTH &&
    trimmed.length <= SUPPORT_MESSAGE_MAX_LENGTH;

  const send = async () => {
    // `canSend` garantit aussi qu'un sujet est choisi (TypeScript le sait).
    if (!canSend) return;
    setSendError(null);
    setIsSending(true);
    try {
      const created = await api.createSupportTicket({ category, message: trimmed, interventionId });
      setData((previous) => [created, ...(previous ?? [])]);
      setMessage('');
      setCategory('');
      setInterventionId(null);
      setSent(true);
    } catch (err) {
      setSendError(
        err instanceof ApiError ? err.message : "Votre demande n'a pas pu être envoyée. Réessayez.",
      );
    } finally {
      setIsSending(false);
    }
  };

  return (
    <>
      <AppBar title="Aide" backTo="/profil" />
      <main className="w-full max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-10 space-y-6">
        <section aria-labelledby="ecrire" className="space-y-3">
          <SectionHeader id="ecrire" title="Écrire à Téranga" />
          <Card className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Un souci avec votre compte, un paiement, un artisan ou un client ? Expliquez-nous : un
              conseiller Téranga vous répond ici.
            </p>
            {interventionId && (
              <p className="flex flex-wrap items-center justify-between gap-2 rounded-field bg-surface-muted p-3 text-sm">
                <span>Votre demande concerne une de vos interventions.</span>
                <Button variant="ghost" size="sm" onClick={() => setInterventionId(null)}>
                  Ne pas la lier
                </Button>
              </p>
            )}
            <SelectField
              label="Sujet"
              value={category}
              onChange={(event) => setCategory(event.target.value as SupportCategory | '')}
            >
              <option value="" disabled>
                Choisissez un sujet
              </option>
              {SUPPORT_CATEGORIES.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </SelectField>
            <TextAreaField
              label="Votre message"
              value={message}
              onChange={(event) => {
                setMessage(event.target.value);
                setSent(false);
              }}
              maxLength={SUPPORT_MESSAGE_MAX_LENGTH}
              rows={5}
              hint={`${trimmed.length} / ${SUPPORT_MESSAGE_MAX_LENGTH} caractères (${SUPPORT_MESSAGE_MIN_LENGTH} minimum)`}
            />
            <p className="flex items-start gap-2 text-caption text-muted-foreground">
              <ShieldCheck aria-hidden className="w-4 h-4 shrink-0 text-primary-emerald" />
              Seuls vous et l&apos;équipe Téranga lisez ce message. Nous vous répondons ici.
            </p>
            {sendError && (
              <p role="alert" className="text-sm text-destructive">
                {sendError}
              </p>
            )}
            {sent && (
              <p role="status" className="text-sm font-semibold text-primary-emerald">
                Demande envoyée. Vous retrouverez la réponse ci-dessous.
              </p>
            )}
            <Button variant="primary" isLoading={isSending} disabled={!canSend} onClick={send}>
              Envoyer
            </Button>
          </Card>
        </section>

        <section aria-labelledby="mes-demandes-aide" className="space-y-3">
          <SectionHeader id="mes-demandes-aide" title="Mes demandes" />
          {isLoading && !tickets ? (
            <div className="space-y-3" aria-busy="true">
              {[0, 1].map((key) => (
                <Skeleton key={key} className="h-24 rounded-card" />
              ))}
            </div>
          ) : error && !tickets ? (
            <ErrorState message={error.message} onRetry={reload} />
          ) : tickets && tickets.length === 0 ? (
            <EmptyState
              icon={<LifeBuoy />}
              title="Aucune demande pour le moment."
              description="Vos demandes et nos réponses apparaîtront ici."
            />
          ) : (
            <ul className="space-y-3">
              {tickets?.map((ticket) => (
                <TicketItem key={ticket.id} ticket={ticket} />
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  );
};
