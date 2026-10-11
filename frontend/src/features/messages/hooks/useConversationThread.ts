import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../../lib/api';
import { REALTIME_CONFIG } from '../../../lib/realtime/config';
import { useDocumentVisible } from '../../../lib/useDocumentVisible';
import type { ChatMessage, ConversationDetail } from '../../../types';
import { useAuth } from '../../auth/hooks/useAuth';
import { useRealtime } from '../realtime/useRealtime';

/** Taille d'une relecture `since` : on reboucle tant que la page est pleine. */
const CATCH_UP_PAGE_SIZE = 100;
/** Délai avant de marquer « lu » (laisse le temps à une rafale d'arriver). */
const MARK_READ_DELAY_MS = 400;

/** Message en cours d'envoi (affiché tout de suite) ou en échec (à renvoyer). */
export interface PendingMessage {
  tempId: string;
  body: string;
  file: File | null;
  /** Aperçu local de l'image pendant l'envoi (URL `blob:`, révoquée ensuite). */
  previewUrl: string | null;
  status: 'sending' | 'failed';
  error: string | null;
  createdAt: string;
}

function toApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError('unknown', 'Une erreur inattendue est survenue. Merci de réessayer.');
}

function newTempId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function createPreview(file: File): string | null {
  return typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : null;
}

function revokePreview(url: string | null): void {
  if (url && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(url);
}

/**
 * État d'un fil de discussion et ses actions.
 *
 * Fiabilité :
 * - REST est la source de vérité : historique chargé par REST, envoi par
 *   REST (persisté avant toute diffusion) ;
 * - temps réel quand il est `open` ; sinon relecture `since` toutes les
 *   quelques secondes (onglet visible seulement), et rattrapage immédiat à
 *   chaque (ré)ouverture du temps réel ou retour sur l'onglet — aucun
 *   message ne peut être perdu pendant une coupure ;
 * - messages dédoublonnés par identifiant et triés par `seq` : une réponse
 *   REST et un événement temps réel du même message ne l'affichent qu'une fois ;
 * - envoi optimiste : le message apparaît aussitôt, se confirme à la
 *   persistance (le texte confirmé est la version masquée par le serveur),
 *   ou passe en échec avec « Réessayer ».
 * Tout s'arrête au démontage (minuteurs, relectures, aperçus d'images).
 */
export function useConversationThread(conversationId: string) {
  const realtime = useRealtime();
  const auth = useAuth();
  const visible = useDocumentVisible();
  const myId = auth.user?.id ?? null;

  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<PendingMessage[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  // Curseur de lecture au CHARGEMENT : place le séparateur « Nouveaux messages ».
  const [initialReadSeq, setInitialReadSeq] = useState(0);

  const mountedRef = useRef(true);
  const lastSeqRef = useRef(0);
  const catchUpInFlightRef = useRef(false);
  const markedSeqRef = useRef(0);
  const pendingRef = useRef<PendingMessage[]>([]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    pendingRef.current = pending;
  }, [pending]);

  // Aperçus d'images révoqués au départ de l'écran (aucune fuite mémoire).
  useEffect(
    () => () => {
      pendingRef.current.forEach((item) => revokePreview(item.previewUrl));
    },
    [],
  );

  const merge = useCallback(
    (incoming: ChatMessage[]) => {
      const relevant = incoming.filter((message) => message.conversationId === conversationId);
      if (relevant.length === 0) return;
      lastSeqRef.current = Math.max(lastSeqRef.current, ...relevant.map((m) => m.seq));
      setMessages((previous) => {
        const byId = new Map(previous.map((message) => [message.id, message]));
        relevant.forEach((message) => byId.set(message.id, message));
        return [...byId.values()].sort((a, b) => a.seq - b.seq);
      });
    },
    [conversationId],
  );

  // Chargement initial (et après « Réessayer ») : motif recommandé par React
  // pour une requête dans un effet -- état modifié seulement dans la
  // réponse, réponse tardive ignorée si l'écran a changé entre-temps.
  // Un fil = une instance du hook : l'écran le monte avec
  // `key={conversationId}`, donc changer de conversation repart d'un état
  // vierge, sans aucun message d'un fil affiché dans un autre.
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    let ignore = false;
    Promise.all([api.getConversation(conversationId), api.listMessages(conversationId)])
      .then(([detail, history]) => {
        if (ignore) return;
        setConversation(detail);
        setInitialReadSeq(detail.myLastReadSeq);
        markedSeqRef.current = detail.myLastReadSeq;
        setMessages(history.items);
        lastSeqRef.current = history.items.at(-1)?.seq ?? 0;
        setHasMore(history.hasMore);
        setError(null);
        setIsLoaded(true);
      })
      .catch((err: unknown) => {
        if (!ignore) setError(toApiError(err));
      })
      .finally(() => {
        if (!ignore) setIsLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [conversationId, reloadKey]);

  /** « Réessayer » après une erreur de chargement (action de l'utilisateur). */
  const reload = useCallback(() => {
    setIsLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  }, []);

  /** Relit tout ce qui est postérieur au dernier message connu. */
  const catchUp = useCallback(async () => {
    if (catchUpInFlightRef.current) return;
    catchUpInFlightRef.current = true;
    try {
      // Reboucle tant que la page revient pleine (longue coupure).
      for (;;) {
        const history = await api.listMessages(conversationId, {
          since: lastSeqRef.current,
          limit: CATCH_UP_PAGE_SIZE,
        });
        if (!mountedRef.current) return;
        merge(history.items);
        if (history.items.length < CATCH_UP_PAGE_SIZE) break;
      }
    } catch {
      // Silencieux : la prochaine relecture réessaiera.
    } finally {
      catchUpInFlightRef.current = false;
    }
  }, [conversationId, merge]);

  // Temps réel : chaque message du fil est ajouté dès sa diffusion.
  useEffect(
    () =>
      realtime.subscribe((event) => {
        if (event.type === 'message.created') merge([event.message]);
      }),
    [realtime, merge],
  );

  // Rattrapage à chaque changement d'état du temps réel ou retour sur l'onglet.
  useEffect(() => {
    if (isLoaded && visible) void catchUp();
  }, [isLoaded, visible, realtime.status, catchUp]);

  // Repli : relecture régulière tant que le temps réel n'est pas ouvert.
  useEffect(() => {
    if (!isLoaded || !visible || realtime.status === 'open') return;
    const timer = setInterval(() => void catchUp(), REALTIME_CONFIG.threadPollIntervalMs);
    return () => clearInterval(timer);
  }, [isLoaded, visible, realtime.status, catchUp]);

  // Marquage « lu » : seulement onglet visible, et seulement s'il existe un
  // message de l'autre partie au-delà de ce qui est déjà marqué.
  useEffect(() => {
    if (!visible || !isLoaded) return;
    const latest = messages.at(-1)?.seq ?? 0;
    const hasUnreadFromOther = messages.some(
      (message) => message.senderId !== myId && message.seq > markedSeqRef.current,
    );
    if (!hasUnreadFromOther) return;
    const timer = setTimeout(() => {
      markedSeqRef.current = Math.max(markedSeqRef.current, latest);
      api
        .markConversationRead(conversationId, latest)
        .then(() => realtime.refreshUnread())
        .catch(() => undefined);
    }, MARK_READ_DELAY_MS);
    return () => clearTimeout(timer);
  }, [messages, visible, isLoaded, myId, conversationId, realtime]);

  const deliver = useCallback(
    async (item: PendingMessage) => {
      try {
        const message = item.file
          ? await api.sendImageMessage(conversationId, item.file, item.body)
          : await api.sendMessage(conversationId, item.body);
        if (!mountedRef.current) return;
        merge([message]);
        setPending((current) => current.filter((p) => p.tempId !== item.tempId));
        revokePreview(item.previewUrl);
      } catch (err) {
        if (!mountedRef.current) return;
        const message = toApiError(err).message;
        setPending((current) =>
          current.map((p) =>
            p.tempId === item.tempId ? { ...p, status: 'failed', error: message } : p,
          ),
        );
      }
    },
    [conversationId, merge],
  );

  const enqueue = useCallback(
    (body: string, file: File | null) => {
      const item: PendingMessage = {
        tempId: newTempId(),
        body,
        file,
        previewUrl: file ? createPreview(file) : null,
        status: 'sending',
        error: null,
        createdAt: new Date().toISOString(),
      };
      setPending((current) => [...current, item]);
      void deliver(item);
    },
    [deliver],
  );

  const send = useCallback(
    (body: string) => {
      const text = body.trim();
      if (text) enqueue(text, null);
    },
    [enqueue],
  );

  const sendImage = useCallback(
    (file: File, caption: string) => enqueue(caption.trim(), file),
    [enqueue],
  );

  const retry = useCallback(
    (tempId: string) => {
      const item = pendingRef.current.find((p) => p.tempId === tempId);
      if (!item) return;
      const again = { ...item, status: 'sending' as const, error: null };
      setPending((current) => current.map((p) => (p.tempId === tempId ? again : p)));
      void deliver(again);
    },
    [deliver],
  );

  const discard = useCallback((tempId: string) => {
    const item = pendingRef.current.find((p) => p.tempId === tempId);
    revokePreview(item?.previewUrl ?? null);
    setPending((current) => current.filter((p) => p.tempId !== tempId));
  }, []);

  const loadOlder = useCallback(async () => {
    const oldest = messages[0];
    if (!hasMore || isLoadingOlder || !oldest) return;
    setIsLoadingOlder(true);
    try {
      const history = await api.listMessages(conversationId, { before: oldest.seq });
      if (!mountedRef.current) return;
      merge(history.items);
      setHasMore(history.hasMore);
    } catch {
      // L'utilisateur peut relancer : le bouton reste affiché.
    } finally {
      if (mountedRef.current) setIsLoadingOlder(false);
    }
  }, [conversationId, hasMore, isLoadingOlder, merge, messages]);

  return {
    conversation,
    messages,
    pending,
    myId,
    initialReadSeq,
    isLoading,
    error,
    hasMore,
    isLoadingOlder,
    realtimeStatus: realtime.status,
    reload,
    loadOlder,
    send,
    sendImage,
    retry,
    discard,
  };
}
