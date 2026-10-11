import { useContext } from 'react';
import { RealtimeContext, type RealtimeContextValue } from './realtime-context';

/** Accès au canal temps réel de la messagerie (statut, événements, non-lus). */
export function useRealtime(): RealtimeContextValue {
  return useContext(RealtimeContext);
}
