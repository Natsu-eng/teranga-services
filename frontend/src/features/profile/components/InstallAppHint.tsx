import React, { useState } from 'react';
import { Share, Smartphone, X } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { IconButton } from '../../../components/ui/IconButton';
import {
  isAppleMobile,
  isRunningStandalone,
  promptInstall,
  useInstallPrompt,
} from '../../../lib/pwa/installPrompt';

/** Mémoire du « Masquer », propre à ce navigateur (simple confort). */
export const INSTALL_HINT_DISMISSED_KEY = 'teranga.installation.masquee';

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(INSTALL_HINT_DISMISSED_KEY) === '1';
  } catch {
    // Stockage indisponible (navigation privée) : le conseil reste proposé.
    return false;
  }
}

function storeDismissed(): void {
  try {
    window.localStorage.setItem(INSTALL_HINT_DISMISSED_KEY, '1');
  } catch {
    // Sans stockage, le choix vaut pour l'écran en cours seulement.
  }
}

/**
 * Conseil discret « Installer l'app » (profil) : Téranga sur l'écran
 * d'accueil, ouverte en plein écran comme une application.
 *
 * - Android / Chrome : bouton qui ouvre la boîte d'installation du navigateur ;
 * - iPhone / iPad : explication du geste Safari (Partager > « Sur l'écran
 *   d'accueil »), Safari n'offrant pas de bouton programmable ;
 * - rien si l'app est déjà installée, si le navigateur ne sait pas
 *   l'installer, ou si l'utilisateur a masqué le conseil.
 */
export const InstallAppHint: React.FC = () => {
  const installPrompt = useInstallPrompt();
  const [dismissed, setDismissed] = useState(readDismissed);

  if (dismissed || isRunningStandalone()) return null;
  const apple = isAppleMobile(window.navigator.userAgent, window.navigator.maxTouchPoints ?? 0);
  if (!installPrompt && !apple) return null;

  const dismiss = () => {
    storeDismissed();
    setDismissed(true);
  };

  return (
    <Card as="aside" aria-labelledby="installer-app" className="flex items-start gap-3">
      <span
        aria-hidden
        className="inline-flex w-10 h-10 shrink-0 items-center justify-center rounded-full bg-emerald-tint text-primary-emerald"
      >
        <Smartphone className="w-5 h-5" />
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <h2 id="installer-app" className="text-sm font-semibold text-foreground">
          Installer l&apos;app
        </h2>
        {installPrompt ? (
          <>
            <p className="text-sm text-muted-foreground">
              Téranga sur votre écran d&apos;accueil, en plein écran, comme une application.
            </p>
            <Button variant="outline" size="sm" onClick={() => void promptInstall()}>
              Installer
            </Button>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Dans Safari, touchez le bouton Partager{' '}
            <Share aria-hidden className="inline w-4 h-4 align-text-bottom" /> puis « Sur
            l&apos;écran d&apos;accueil » : Téranga s&apos;ouvrira en plein écran, comme une
            application.
          </p>
        )}
      </div>
      <IconButton label="Masquer ce conseil" size="sm" onClick={dismiss}>
        <X aria-hidden className="w-4 h-4" />
      </IconButton>
    </Card>
  );
};
