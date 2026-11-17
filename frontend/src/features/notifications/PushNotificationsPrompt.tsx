import React, { useEffect, useMemo, useState } from 'react';
import { Bell, Share, X } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { IconButton } from '../../components/ui/IconButton';
import { api } from '../../lib/api';
import type { PushConfig } from '../../lib/api/types';
import { browserPush, enablePushNotifications, type PushBrowser } from '../../lib/push/webPush';

/** Mémoire du « Plus tard », propre à ce navigateur (simple confort). */
export const PUSH_PROMPT_DISMISSED_KEY = 'teranga.notifications.invitation-masquee';

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(PUSH_PROMPT_DISMISSED_KEY) === '1';
  } catch {
    // Stockage indisponible (navigation privée) : l'invitation reste proposée.
    return false;
  }
}

function storeDismissed(): void {
  try {
    window.localStorage.setItem(PUSH_PROMPT_DISMISSED_KEY, '1');
  } catch {
    // Sans stockage, le choix vaut pour l'écran en cours seulement.
  }
}

type Outcome = 'idle' | 'busy' | 'enabled' | 'denied' | 'error';

interface PushNotificationsPromptProps {
  /** Injection pour les tests ; par défaut, le vrai navigateur. */
  browser?: PushBrowser;
}

/**
 * Invitation DISCRÈTE à activer les notifications de nouveaux messages
 * (écran Messages). Jamais de demande de permission au chargement : la
 * boîte du navigateur ne s'ouvre qu'au clic sur « Activer ».
 *
 * N'apparaît que si c'est utile : notifications activées côté serveur, et
 * permission encore à demander (« Plus tard » la masque sur ce navigateur ;
 * déjà accordée, la resynchronisation s'en charge ; refusée, rien à faire
 * d'ici). Sur iPhone/iPad dans Safari, explique qu'il faut installer l'app
 * (le Web Push n'y existe que pour l'app installée, iOS 16.4+).
 */
export const PushNotificationsPrompt: React.FC<PushNotificationsPromptProps> = ({ browser }) => {
  const push = useMemo(() => browser ?? browserPush(), [browser]);
  const relevant = push.supported || push.needsInstall;
  const [dismissed, setDismissed] = useState(readDismissed);
  const [config, setConfig] = useState<PushConfig | null>(null);
  const [outcome, setOutcome] = useState<Outcome>('idle');

  useEffect(() => {
    if (dismissed || !relevant) return;
    let alive = true;
    api
      .getPushConfig()
      .then((loaded) => {
        if (alive) setConfig(loaded);
      })
      // Serveur injoignable : pas d'invitation (rien de cassé pour autant).
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [dismissed, relevant]);

  if (dismissed || !relevant || !config?.enabled) return null;

  const dismiss = () => {
    storeDismissed();
    setDismissed(true);
  };

  const enable = () => {
    setOutcome('busy');
    enablePushNotifications(api, push, config)
      .then((result) => {
        if (result === 'enabled') setOutcome('enabled');
        else if (result === 'denied') setOutcome('denied');
        else if (result === 'dismissed') setOutcome('idle');
        else setOutcome('error');
      })
      .catch(() => setOutcome('error'));
  };

  if (outcome === 'enabled') {
    return (
      <p role="status" className="text-sm text-primary-emerald font-semibold">
        Notifications activées sur cet appareil.
      </p>
    );
  }

  // Invitation encore pertinente : permission jamais demandée sur ce navigateur.
  const askable = push.supported && push.permission() === 'default';
  if (!push.needsInstall && !askable && outcome !== 'denied') return null;

  let content: React.ReactNode;
  if (push.needsInstall) {
    content = (
      <p className="text-sm text-muted-foreground">
        Sur iPhone et iPad, installez d&apos;abord l&apos;app : dans Safari, touchez Partager{' '}
        <Share aria-hidden className="inline w-4 h-4 align-text-bottom" /> puis « Sur l&apos;écran
        d&apos;accueil », et ouvrez Téranga depuis l&apos;icône.
      </p>
    );
  } else if (outcome === 'denied') {
    content = (
      <p role="status" className="text-sm text-muted-foreground">
        Notifications bloquées sur ce navigateur. Vous pouvez les autoriser dans ses réglages.
      </p>
    );
  } else {
    content = (
      <>
        <p className="text-sm text-muted-foreground">
          Recevez une notification sur cet appareil quand on vous écrit, même app fermée.
        </p>
        {outcome === 'error' && (
          <p role="alert" className="text-sm text-destructive">
            Impossible d&apos;activer les notifications pour le moment. Réessayez plus tard.
          </p>
        )}
        <Button variant="outline" size="sm" isLoading={outcome === 'busy'} onClick={enable}>
          Activer
        </Button>
      </>
    );
  }

  return (
    <Card as="aside" aria-labelledby="notifications-push" className="flex items-start gap-3">
      <span
        aria-hidden
        className="inline-flex w-10 h-10 shrink-0 items-center justify-center rounded-full bg-emerald-tint text-primary-emerald"
      >
        <Bell className="w-5 h-5" />
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <h2 id="notifications-push" className="text-sm font-semibold text-foreground">
          Ne manquez aucun message
        </h2>
        {content}
      </div>
      <IconButton label="Masquer cette invitation" size="sm" onClick={dismiss}>
        <X aria-hidden className="w-4 h-4" />
      </IconButton>
    </Card>
  );
};
