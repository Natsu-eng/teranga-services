import React, { useEffect, useRef } from 'react';
import { ExternalLink, Lock, MessagesSquare, RefreshCw, ShieldCheck } from 'lucide-react';
import { Link, useParams } from 'react-router';
import { AppBar } from '../../components/ui/AppBar';
import { Button, ButtonLink } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { cn } from '../../lib/cn';
import { formatDayLabel, isSameDay } from '../../lib/datetime';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { MessageBubble, PendingBubble } from './components/MessageBubble';
import { MessageComposer } from './components/MessageComposer';
import { useConversationThread } from './hooks/useConversationThread';
import { useRealtime } from './realtime/useRealtime';

/**
 * Fil de discussion (/messages/:conversationId). Monté avec
 * `key={conversationId}` : changer de fil repart d'un état vierge.
 */
export const ConversationScreen: React.FC = () => {
  const { conversationId = '' } = useParams<{ conversationId: string }>();
  return <ConversationThread key={conversationId} conversationId={conversationId} />;
};

const DaySeparator: React.FC<{ iso: string }> = ({ iso }) => (
  <li aria-hidden className="flex justify-center py-1">
    <span className="rounded-full bg-surface-muted px-3 py-1 text-caption font-semibold text-muted-foreground">
      {formatDayLabel(iso)}
    </span>
  </li>
);

/** Non-participant ou fil inexistant : même écran, aucun indice. */
const ThreadUnavailable: React.FC<{ backTo: string; isPro: boolean }> = ({ backTo, isPro }) => (
  <>
    <AppBar title="Discussion" backTo={backTo} tone={isPro ? 'pro' : 'light'} />
    <main className="w-full max-w-2xl mx-auto px-4 pt-8">
      <EmptyState
        icon={<Lock />}
        title="Cette discussion est introuvable."
        description="Elle n'existe pas ou ne vous concerne pas."
      >
        <ButtonLink to="/messages" variant="outline" size="sm">
          Mes messages
        </ButtonLink>
      </EmptyState>
    </main>
  </>
);

const ConversationThread: React.FC<{ conversationId: string }> = ({ conversationId }) => {
  const auth = useAuth();
  const isPro = toDisplayRole(auth.role) === 'artisan';
  const thread = useConversationThread(conversationId);
  const { setViewingConversation } = useRealtime();
  const endRef = useRef<HTMLDivElement>(null);
  const lastCountRef = useRef(0);
  const { conversation, messages, pending } = thread;

  // Fil à l'écran : le serveur n'envoie pas de notification push pour ses
  // nouveaux messages (déjà visibles ici) ; signal retiré en quittant le fil.
  useEffect(() => {
    setViewingConversation(conversationId);
    return () => setViewingConversation(null);
  }, [conversationId, setViewingConversation]);

  // Défile vers le bas à l'ouverture et à chaque nouveau message.
  const total = messages.length + pending.length;
  useEffect(() => {
    if (total > lastCountRef.current) {
      endRef.current?.scrollIntoView({ block: 'end' });
    }
    lastCountRef.current = total;
  }, [total]);

  if (thread.isLoading && !conversation) {
    return (
      <>
        <AppBar title="Discussion" backTo="/messages" tone={isPro ? 'pro' : 'light'} />
        <main className="w-full max-w-2xl mx-auto px-4 pt-6 space-y-4" aria-busy="true">
          <Skeleton className="h-12 w-2/3" />
          <Skeleton className="h-12 w-1/2 ml-auto" />
          <Skeleton className="h-16 w-3/4" />
        </main>
      </>
    );
  }

  if (thread.error && !conversation) {
    if (thread.error.code === 'forbidden' || thread.error.code === 'not_found') {
      return <ThreadUnavailable backTo="/messages" isPro={isPro} />;
    }
    return (
      <>
        <AppBar title="Discussion" backTo="/messages" tone={isPro ? 'pro' : 'light'} />
        <main className="w-full max-w-2xl mx-auto px-4 pt-6">
          <ErrorState message={thread.error.message} onRetry={thread.reload} />
        </main>
      </>
    );
  }

  if (!conversation) return null;

  const other = conversation.otherParty;
  const followUpLink = isPro ? '/pro' : '/mes-interventions';
  const firstUnreadIndex = messages.findIndex(
    (message) => message.senderId !== thread.myId && message.seq > thread.initialReadSeq,
  );

  return (
    <>
      <AppBar
        title={other.displayName}
        subtitle={conversation.tradeLabel ?? undefined}
        backTo="/messages"
        tone={isPro ? 'pro' : 'light'}
        actions={
          !isPro && other.artisanProfileId ? (
            <Link
              to={`/artisans/${other.artisanProfileId}`}
              aria-label={`Voir la fiche de ${other.displayName}`}
              title={`Voir la fiche de ${other.displayName}`}
              className="inline-flex w-11 h-11 items-center justify-center rounded-full text-foreground hover:bg-surface-muted"
            >
              <ExternalLink aria-hidden className="w-5 h-5" />
            </Link>
          ) : undefined
        }
      />

      <main className="w-full max-w-2xl mx-auto flex-1 px-4 pt-4 pb-32 space-y-4">
        <p className="flex items-start gap-2 rounded-field bg-emerald-tint px-3 py-2 text-xs text-foreground">
          <ShieldCheck aria-hidden className="w-4 h-4 shrink-0 text-primary-emerald" />
          <span>
            Discussion liée à votre mise en relation. Numéros et e-mails sont masqués
            automatiquement ; les photos ne sont visibles que de vous deux.{' '}
            <Link
              to={followUpLink}
              className="font-semibold text-primary underline-offset-4 hover:underline"
            >
              {isPro ? 'Voir la demande' : 'Voir le devis et le suivi'}
            </Link>
          </span>
        </p>

        {thread.hasMore && (
          <div className="flex justify-center">
            <Button
              variant="ghost"
              size="sm"
              isLoading={thread.isLoadingOlder}
              onClick={() => void thread.loadOlder()}
            >
              Messages précédents
            </Button>
          </div>
        )}

        {messages.length === 0 && pending.length === 0 ? (
          <EmptyState
            tone="plain"
            icon={<MessagesSquare />}
            title={`Écrivez à ${other.displayName}`}
            description={
              isPro
                ? 'Posez vos questions sur le besoin du client avant de proposer votre devis.'
                : "Précisez votre besoin, l'accès ou vos disponibilités : l'artisan s'en sert pour son devis."
            }
          />
        ) : (
          <ol aria-label="Messages" aria-live="polite" className="space-y-3">
            {messages.map((message, index) => {
              const previous = messages[index - 1];
              return (
                <React.Fragment key={message.id}>
                  {(!previous || !isSameDay(previous.createdAt, message.createdAt)) && (
                    <DaySeparator iso={message.createdAt} />
                  )}
                  {index === firstUnreadIndex && (
                    <li className="flex items-center gap-2 py-1 text-caption font-semibold uppercase tracking-wider text-primary-emerald">
                      <span aria-hidden className="h-px flex-1 bg-emerald-tint-strong" />
                      Nouveaux messages
                      <span aria-hidden className="h-px flex-1 bg-emerald-tint-strong" />
                    </li>
                  )}
                  <MessageBubble
                    message={message}
                    mine={message.senderId === thread.myId}
                    otherPartyName={other.displayName}
                  />
                </React.Fragment>
              );
            })}
            {pending.map((item) => (
              <PendingBubble
                key={item.tempId}
                item={item}
                onRetry={thread.retry}
                onDiscard={thread.discard}
              />
            ))}
          </ol>
        )}
        <div ref={endRef} />
      </main>

      <div className="fixed bottom-0 inset-x-0 z-40 bg-surface/95 backdrop-blur-md shadow-bar px-3 pt-3 pb-safe">
        <div className="max-w-2xl mx-auto space-y-2 pb-1">
          {/* Discret, jamais alarmant : la bascule en relecture est automatique. */}
          {thread.realtimeStatus === 'unavailable' && (
            <p
              role="status"
              className="flex items-center justify-center gap-1.5 text-caption text-muted-foreground"
            >
              <RefreshCw aria-hidden className="w-3 h-3" />
              Connexion instable : les nouveaux messages arrivent avec quelques secondes de délai.
            </p>
          )}
          {conversation.canSend ? (
            <MessageComposer onSend={thread.send} onSendImage={thread.sendImage} />
          ) : (
            <p
              className={cn(
                'flex items-center justify-center gap-2 rounded-field bg-surface-muted px-3 py-3 text-sm text-muted-foreground',
              )}
            >
              <Lock aria-hidden className="w-4 h-4" />
              Mise en relation refusée : cette discussion est en lecture seule.
            </p>
          )}
        </div>
      </div>
    </>
  );
};
