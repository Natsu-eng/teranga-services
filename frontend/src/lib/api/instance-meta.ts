import { apiRequest } from './http';

/** Réponse de `GET /api/v1/meta` (backend app/schemas/meta.py). */
export interface InstanceMeta {
  environment: 'development' | 'test' | 'staging' | 'production';
  /** Vrai si des numéros de test se connectent sans SMS (staging uniquement). */
  otp_test_mode: boolean;
}

/** Informations publiques de l'instance : lecture sans compte ni jeton. */
export function fetchInstanceMeta(): Promise<InstanceMeta> {
  return apiRequest<InstanceMeta>('/meta', { skipAuth: true });
}
