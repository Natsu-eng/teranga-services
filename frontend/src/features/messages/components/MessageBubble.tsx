import React from 'react';
import { AlertCircle, ShieldCheck } from 'lucide-react';
import { Spinner } from '../../../components/ui/Spinner';
import { cn } from '../../../lib/cn';
import { formatTime } from '../../../lib/datetime';
import type { ChatMessage } from '../../../types';
import type { PendingMessage } from '../hooks/useConversationThread';
import { AttachmentImage } from './AttachmentImage';

function Bubble({
  mine,
  children,
}: {
  mine: boolean;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <div
      className={cn(
        'max-w-[85%] sm:max-w-[70%] rounded-card px-4 py-2.5 space-y-2 break-words whitespace-pre-wrap',
        mine
          ? 'bg-primary-emerald text-white rounded-br-md'
          : 'bg-surface text-foreground shadow-card rounded-bl-md',
      )}
    >
      {children}
    </div>
  );
}

/**
 * Avertissement de transparence sous un message dont des coordonnées ont
 * été masquées : on dit ce qui s'est passé et pourquoi, sans jamais
 * réafficher la donnée retirée.
 */
const MaskedNotice: React.FC<{ mine: boolean }> = ({ mine }) => (
  <p className="flex items-start gap-1.5 text-xs text-muted-foreground max-w-[85%] sm:max-w-[70%]">
    <ShieldCheck aria-hidden className="w-3.5 h-3.5 shrink-0 mt-0.5 text-primary-emerald" />
    {mine
      ? 'Vos coordonnées ont été masquées : les échanges et devis passent par Téranga, pour votre protection.'
      : 'Des coordonnées ont été masquées dans ce message, pour votre protection.'}
  </p>
);

interface MessageBubbleProps {
  message: ChatMessage;
  mine: boolean;
  otherPartyName: string;
}

/** Message enregistré (confirmé par le serveur). */
export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, mine, otherPartyName }) => (
  <li className={cn('flex flex-col gap-1', mine ? 'items-end' : 'items-start')}>
    <span className="sr-only">{mine ? 'Vous' : otherPartyName} :</span>
    <Bubble mine={mine}>
      {message.hasAttachment && (
        <AttachmentImage
          conversationId={message.conversationId}
          messageId={message.id}
          alt={mine ? 'Photo que vous avez envoyée' : `Photo envoyée par ${otherPartyName}`}
        />
      )}
      {message.body && <p>{message.body}</p>}
    </Bubble>
    <time dateTime={message.createdAt} className="px-1 text-caption text-muted-foreground">
      {formatTime(message.createdAt)}
    </time>
    {message.contactMasked && <MaskedNotice mine={mine} />}
  </li>
);

interface PendingBubbleProps {
  item: PendingMessage;
  onRetry: (tempId: string) => void;
  onDiscard: (tempId: string) => void;
}

/**
 * Message affiché aussitôt (envoi optimiste) : « Envoi… » le temps de la
 * persistance, puis remplacé par le message confirmé ; en cas d'échec, il
 * reste visible avec la raison, « Réessayer » et « Supprimer ».
 */
export const PendingBubble: React.FC<PendingBubbleProps> = ({ item, onRetry, onDiscard }) => (
  <li className="flex flex-col items-end gap-1">
    <div className={cn(item.status === 'sending' && 'opacity-70')}>
      <Bubble mine>
        {item.previewUrl && (
          <img
            src={item.previewUrl}
            alt="Photo en cours d'envoi"
            className="block max-h-72 w-auto max-w-full rounded-field object-cover"
          />
        )}
        {item.body && <p>{item.body}</p>}
      </Bubble>
    </div>
    {item.status === 'sending' ? (
      <span className="flex items-center gap-1.5 px-1 text-caption text-muted-foreground">
        <Spinner label={null} size="sm" />
        Envoi…
      </span>
    ) : (
      <div role="alert" className="flex flex-col items-end gap-1 px-1 text-right">
        <span className="flex items-center gap-1 text-xs text-destructive">
          <AlertCircle aria-hidden className="w-3.5 h-3.5" />
          {item.error ?? "Le message n'a pas pu être envoyé."}
        </span>
        <span className="flex gap-3">
          <button
            type="button"
            onClick={() => onRetry(item.tempId)}
            className="text-xs font-semibold text-primary-emerald underline-offset-4 hover:underline cursor-pointer"
          >
            Réessayer
          </button>
          <button
            type="button"
            onClick={() => onDiscard(item.tempId)}
            className="text-xs font-semibold text-muted-foreground underline-offset-4 hover:underline cursor-pointer"
          >
            Supprimer
          </button>
        </span>
      </div>
    )}
  </li>
);
