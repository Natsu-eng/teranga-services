import { useCallback, useEffect } from 'react';
import type { ChatMessage } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

// How long after sending a message we re-fetch to pick up the mock's
// simulated artisan auto-reply (see src/lib/api/mock.ts sendChatMessage).
const AUTO_REPLY_REFRESH_DELAY_MS = 2000;
const DEVIS_CONFIRMATION_DELAY_MS = 600;

export function useChat(conversationId: string) {
  const { data, isLoading, error, run, reload, setData } = useAsyncResource<ChatMessage[]>();

  useEffect(() => {
    run(() => api.getChatMessages(conversationId));
  }, [run, conversationId]);

  const sendMessage = useCallback(
    async (text: string) => {
      const message = await api.sendChatMessage(conversationId, text);
      setData((prev) => [...(prev ?? []), message]);

      // Resolve only once the reply has landed, so callers can drive a
      // "typing…" indicator for exactly as long as the reply takes.
      await new Promise((resolve) => setTimeout(resolve, AUTO_REPLY_REFRESH_DELAY_MS));
      run(() => api.getChatMessages(conversationId));
    },
    [conversationId, run, setData],
  );

  const acceptDevis = useCallback(() => {
    setData(
      (prev) =>
        prev?.map((msg) => (msg.devis ? { ...msg, devis: { ...msg.devis, status: 'accepted' } } : msg)) ??
        prev,
    );

    setTimeout(() => {
      setData((prev) => [
        ...(prev ?? []),
        {
          id: `msg-confirm-${Date.now()}`,
          sender: 'system',
          text: "✅ Devis accepté ! Le paiement sera bloqué en sécurité jusqu'à la fin des travaux.",
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    }, DEVIS_CONFIRMATION_DELAY_MS);
  }, [setData]);

  return { data, isLoading, error, reload, sendMessage, acceptDevis };
}
