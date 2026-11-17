import React from 'react';
import { Camera, MessagesSquare, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router';
import { Avatar } from '../../components/ui/Avatar';
import { ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { cardClasses } from '../../components/ui/styles';
import { cn } from '../../lib/cn';
import { formatShortTimestamp } from '../../lib/datetime';
import type { ConversationSummary } from '../../types';
import { useAuth } from '../auth/hooks/useAuth';
import { PushNotificationsPrompt } from '../notifications/PushNotificationsPrompt';
import { toDisplayRole } from '../auth/role';
import { useConversationList } from './hooks/useConversationList';

function preview(conversation: ConversationSummary): React.ReactNode {
  const last = conversation.lastMessage;
  if (!last) return <span className="italic">Aucun message pour le moment</span>;
  const prefix = last.fromMe ? 'Vous : ' : '';
  if (last.hasAttachment && !last.body) {
    return (
      <span className="inline-flex items-center gap-1">
        {prefix}
        <Camera aria-hidden className="w-3.5 h-3.5" />
        Photo
      </span>
    );
  }
  return `${prefix}${last.body}`;
}

const ConversationRow: React.FC<{ conversation: ConversationSummary }> = ({ conversation }) => {
  const unread = conversation.unreadCount > 0;
  const other = conversation.otherParty;
  return (
    <li>
      <Link
        to={`/messages/${conversation.id}`}
        className={cardClasses({ interactive: true, className: 'flex items-center gap-3' })}
      >
        <Avatar name={other.displayName} src={other.avatarUrl} size="md" decorative />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <p className={cn('truncate text-foreground', unread ? 'font-bold' : 'font-semibold')}>
              {other.displayName}
            </p>
            <time
              dateTime={conversation.lastActivityAt}
              className={cn(
                'shrink-0 text-caption',
                unread ? 'font-semibold text-primary-emerald' : 'text-muted-foreground',
              )}
            >
              {formatShortTimestamp(conversation.lastActivityAt)}
            </time>
          </div>
          {conversation.tradeLabel && (
            <p className="text-xs text-muted-foreground">{conversation.tradeLabel}</p>
          )}
          <div className="flex items-center justify-between gap-2">
            <p
              className={cn(
                'truncate text-sm',
                unread ? 'text-foreground font-medium' : 'text-muted-foreground',
              )}
            >
              {preview(conversation)}
            </p>
            {unread && (
              <span className="shrink-0 inline-flex min-w-6 h-6 items-center justify-center rounded-full bg-primary-emerald px-1.5 text-xs font-bold text-white">
                <span className="sr-only">
                  {conversation.unreadCount} message{conversation.unreadCount > 1 ? 's' : ''} non lu
                  {conversation.unreadCount > 1 ? 's' : ''}
                </span>
                <span aria-hidden>{conversation.unreadCount}</span>
              </span>
            )}
          </div>
        </div>
      </Link>
    </li>
  );
};

/**
 * Liste des discussions (/messages), client comme artisan. Chaque
 * discussion est rattachée à une mise en relation réelle : elle apparaît
 * dès qu'un client a envoyé une demande à un artisan.
 */
export const MessagesScreen: React.FC = () => {
  const auth = useAuth();
  const isPro = toDisplayRole(auth.role) === 'artisan';
  const { data: conversations, isLoading, error, reload } = useConversationList();

  return (
    <main className="max-w-3xl mx-auto px-4 md:px-8 pt-2 space-y-5">
      <SectionHeader as="h1" size="lg" title="Messages" />

      <Card tone="tint" padding="sm" className="flex items-start gap-2 text-sm">
        <ShieldCheck aria-hidden className="w-4 h-4 shrink-0 mt-0.5 text-primary-emerald" />
        <span>
          Échangez en toute sécurité : les numéros de téléphone et e-mails sont masqués
          automatiquement, et les photos ne sont visibles que de vous deux.
        </span>
      </Card>

      <PushNotificationsPrompt />

      {isLoading && conversations === null ? (
        <ul className="space-y-3" aria-busy="true">
          {[0, 1, 2].map((key) => (
            <li key={key}>
              <Card className="flex items-center gap-3">
                <Skeleton className="w-14 h-14 rounded-full shrink-0" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-1/2" />
                  <Skeleton className="h-3 w-3/4" />
                </div>
              </Card>
            </li>
          ))}
        </ul>
      ) : error && conversations === null ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : conversations && conversations.length === 0 ? (
        <EmptyState
          icon={<MessagesSquare />}
          title="Aucune discussion pour le moment."
          description={
            isPro
              ? "Une discussion s'ouvre dès qu'un client vous envoie une demande."
              : "Une discussion s'ouvre dès que vous envoyez une demande à un artisan."
          }
        >
          {!isPro && (
            <ButtonLink to="/recherche" variant="primary" size="sm">
              Trouver un artisan
            </ButtonLink>
          )}
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {(conversations ?? []).map((conversation) => (
            <ConversationRow key={conversation.id} conversation={conversation} />
          ))}
        </ul>
      )}
    </main>
  );
};
