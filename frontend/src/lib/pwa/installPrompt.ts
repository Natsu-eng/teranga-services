import { useSyncExternalStore } from 'react';

/**
 * Invitation à installer l'application (PWA).
 *
 * - Android / Chrome : le navigateur émet `beforeinstallprompt` quand l'app
 *   est installable. On garde l'événement (capturé dès le démarrage, voir
 *   src/main.tsx) pour proposer « Installer l'app » au bon moment, depuis
 *   un bouton discret, plutôt qu'une bannière imposée.
 * - iPhone / iPad : Safari n'émet pas cet événement ; l'installation passe
 *   par Partager > « Sur l'écran d'accueil ». On l'explique simplement.
 * - Déjà installée (ouverte en plein écran) : on ne propose rien.
 */

/** Événement non standard de Chromium (absent des types DOM de TypeScript). */
export interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

let deferredPrompt: BeforeInstallPromptEvent | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

/** À appeler une fois au démarrage : l'événement peut survenir très tôt. */
export function captureInstallPrompt(win: Window = window): void {
  win.addEventListener('beforeinstallprompt', (event) => {
    // Pas de mini-bannière automatique du navigateur : l'invitation reste
    // discrète, à l'initiative de l'utilisateur (profil).
    event.preventDefault();
    deferredPrompt = event as BeforeInstallPromptEvent;
    notify();
  });
  win.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    notify();
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): BeforeInstallPromptEvent | null {
  return deferredPrompt;
}

/** L'invitation d'installation disponible (Android/Chrome), ou null. */
export function useInstallPrompt(): BeforeInstallPromptEvent | null {
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}

/** Affiche la boîte d'installation du navigateur ; vrai si l'utilisateur accepte. */
export async function promptInstall(): Promise<boolean> {
  const event = deferredPrompt;
  if (!event) return false;
  // Un événement ne sert qu'une fois (règle du navigateur).
  deferredPrompt = null;
  notify();
  await event.prompt();
  const { outcome } = await event.userChoice;
  return outcome === 'accepted';
}

/** Vrai si l'app tourne déjà installée (plein écran, sans barre du navigateur). */
export function isRunningStandalone(win: Window = window): boolean {
  const displayStandalone = win.matchMedia?.('(display-mode: standalone)').matches === true;
  // Safari iOS : propriété historique, non standard.
  const iosStandalone = (win.navigator as Navigator & { standalone?: boolean }).standalone === true;
  return displayStandalone || iosStandalone;
}

/** iPhone, iPod ou iPad (iPadOS se présente comme un Mac tactile). */
export function isAppleMobile(userAgent: string, maxTouchPoints: number): boolean {
  if (/iPhone|iPad|iPod/.test(userAgent)) return true;
  return /Macintosh/.test(userAgent) && maxTouchPoints > 1;
}

/** Réservé aux tests : remet l'état du module à zéro. */
export function resetInstallPromptForTests(): void {
  deferredPrompt = null;
  notify();
}
