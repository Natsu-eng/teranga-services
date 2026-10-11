import { useEffect, useRef } from 'react';
import { api } from '../../../lib/api';
import { REALTIME_CONFIG } from '../../../lib/realtime/config';
import { useAsyncResource } from '../../../lib/useAsyncResource';
import { useDocumentVisible } from '../../../lib/useDocumentVisible';
import type { ConversationSummary } from '../../../types';
import { useRealtime } from '../realtime/useRealtime';

/** Regroupe les relectures déclenchées par une rafale d'événements. */
const REFRESH_DEBOUNCE_MS = 400;

/**
 * Liste « Messages » : relue à chaque événement temps réel (dernier message,
 * non-lus), et toutes les 30 s en repli quand le temps réel est
 * indisponible — onglet visible seulement. Les données affichées restent en
 * place pendant une relecture (pas de clignotement).
 */
export function useConversationList() {
  const { data, isLoading, error, run, reload } = useAsyncResource<ConversationSummary[]>();
  const realtime = useRealtime();
  const visible = useDocumentVisible();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    run(() => api.listConversations());
  }, [run]);

  useEffect(() => {
    const unsubscribe = realtime.subscribe(() => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(reload, REFRESH_DEBOUNCE_MS);
    });
    return () => {
      unsubscribe();
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [realtime, reload]);

  useEffect(() => {
    if (!visible || realtime.status === 'open') return;
    const timer = setInterval(reload, REALTIME_CONFIG.listPollIntervalMs);
    return () => clearInterval(timer);
  }, [visible, realtime.status, reload]);

  return { data, isLoading, error, reload };
}
