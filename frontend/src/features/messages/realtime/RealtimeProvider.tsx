import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../../lib/api';
import { resolveApiBaseUrl } from '../../../lib/api/base-url';
import { REALTIME_CONFIG } from '../../../lib/realtime/config';
import {
  RealtimeConnection,
  type RealtimeConnectionOptions,
  type RealtimeStatus,
} from '../../../lib/realtime/RealtimeConnection';
import { resolveRealtimeUrl } from '../../../lib/realtime/url';
import { useDocumentVisible } from '../../../lib/useDocumentVisible';
import { useAuth } from '../../auth/hooks/useAuth';
import {
  RealtimeContext,
  type RealtimeContextValue,
  type RealtimeListener,
} from './realtime-context';

/** Regroupe les recomptes déclenchés par une rafale d'événements. */
const UNREAD_REFRESH_DEBOUNCE_MS = 300;

interface RealtimeProviderProps {
  children: React.ReactNode;
  /** Injection pour les tests ; par défaut, une vraie connexion WebSocket. */
  createConnection?: (options: RealtimeConnectionOptions) => RealtimeConnection;
}

/**
 * Un seul canal temps réel pour toute l'application, partagé par la liste
 * des conversations, le fil ouvert et le badge de la navigation.
 *
 * Ouvert seulement quand c'est utile : compte client ou artisan connecté ET
 * onglet visible. Fermé dès que l'onglet passe en arrière-plan ou à la
 * déconnexion (aucune socket inutile), rouvert au retour. Tant qu'il n'est
 * pas `open`, chaque écran relit lui-même l'API REST : la bascule est
 * invisible pour l'utilisateur.
 */
export const RealtimeProvider: React.FC<RealtimeProviderProps> = ({
  children,
  createConnection,
}) => {
  const auth = useAuth();
  const visible = useDocumentVisible();
  const userId = auth.user?.id ?? null;
  const enabled = auth.isAuthenticated && (auth.role === 'client' || auth.role === 'artisan');

  // Connexion autorisée et utile en ce moment.
  const active = enabled && visible && userId !== null;
  const [status, setStatus] = useState<RealtimeStatus>('idle');
  // Compteur rattaché au compte qui l'a lu : jamais celui d'une session
  // précédente affiché à un autre compte.
  const [unread, setUnread] = useState<{ userId: string; count: number } | null>(null);
  const listenersRef = useRef(new Set<RealtimeListener>());
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const subscribe = useCallback((listener: RealtimeListener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  const refreshUnread = useCallback(() => {
    if (!enabled) return;
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => {
      refreshTimerRef.current = null;
      api
        .getUnreadMessageCount()
        .then((count) => {
          if (userId) setUnread({ userId, count });
        })
        // Échec réseau : on garde la dernière valeur connue plutôt qu'un 0 trompeur.
        .catch(() => undefined);
    }, UNREAD_REFRESH_DEBOUNCE_MS);
  }, [enabled, userId]);

  // Connexion : ouverte seulement si utile, fermée sinon.
  useEffect(() => {
    if (!active) return;
    const options: RealtimeConnectionOptions = {
      url: resolveRealtimeUrl(
        resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
        window.location,
      ),
      getTicket: async () => (await api.createRealtimeTicket()).ticket,
    };
    const connection = createConnection
      ? createConnection(options)
      : new RealtimeConnection(options);
    const offStatus = connection.onStatus(setStatus);
    const offEvent = connection.onEvent((event) => {
      listenersRef.current.forEach((listener) => listener(event));
    });
    connection.start();
    return () => {
      offStatus();
      offEvent();
      connection.stop();
    };
  }, [active, createConnection]);

  // Non-lus : relus à l'ouverture de session, au retour sur l'onglet et à
  // chaque (re)connexion du temps réel (rattrapage après une coupure).
  useEffect(() => {
    if (enabled && visible) refreshUnread();
  }, [enabled, visible, status, refreshUnread]);

  // Un message d'autrui ou une lecture (sur un autre appareil) : recompte.
  useEffect(
    () =>
      subscribe((event) => {
        if (event.type === 'message.created' && event.message.senderId === userId) return;
        refreshUnread();
      }),
    [subscribe, refreshUnread, userId],
  );

  // Repli : sans temps réel, le badge est relu à intervalle régulier
  // (onglet visible seulement).
  useEffect(() => {
    if (!active || status === 'open') return;
    const timer = setInterval(refreshUnread, REALTIME_CONFIG.listPollIntervalMs);
    return () => clearInterval(timer);
  }, [active, status, refreshUnread]);

  useEffect(
    () => () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    },
    [],
  );

  // Valeurs dérivées au rendu (pas de remise à zéro dans un effet) : hors
  // connexion active, le statut est « idle » ; hors session, pas de compteur.
  const effectiveStatus: RealtimeStatus = active ? status : 'idle';
  const unreadCount = enabled && unread && unread.userId === userId ? unread.count : null;

  const value = useMemo<RealtimeContextValue>(
    () => ({ status: effectiveStatus, subscribe, unreadCount, refreshUnread }),
    [effectiveStatus, subscribe, unreadCount, refreshUnread],
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
};
