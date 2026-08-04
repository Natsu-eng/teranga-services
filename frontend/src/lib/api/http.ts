import { ApiError, type ApiErrorCode } from './types';
import { authStore, type TokenPair } from './auth-store';

const API_BASE = '/api/v1';
const DEFAULT_TIMEOUT_MS = 10_000;

const NETWORK_ERROR_MESSAGE = "Impossible de contacter le serveur. Vérifiez votre connexion.";
const SESSION_EXPIRED_MESSAGE = 'Votre session a expiré, merci de vous reconnecter.';

interface BackendErrorBody {
  error?: { code?: string; message?: string };
}

/** Backend statuses -> the four ApiErrorCode values screens already know how to render. */
function errorCodeForStatus(status: number): ApiErrorCode {
  if (status === 404) return 'not_found';
  if (status >= 400 && status < 500) return 'validation';
  if (status >= 500) return 'network';
  return 'unknown';
}

function extractBackendMessage(body: unknown): string | null {
  if (body && typeof body === 'object' && 'error' in body) {
    const message = (body as BackendErrorBody).error?.message;
    if (typeof message === 'string' && message.length > 0) return message;
  }
  return null;
}

/** Defensive JSON parse: an empty body, non-JSON body, or a 204 all resolve to `null` rather than throwing. */
async function parseJsonBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Upload multipart (ex. documents de vérification) — mutuellement exclusif avec `body`. Jamais sérialisé en JSON ; le navigateur pose lui-même la frontière multipart, donc aucun Content-Type n'est fixé explicitement ici. */
  formData?: FormData;
  /** Auth endpoints (request-otp, verify-otp, refresh) don't carry a token and must never trigger the 401 refresh dance on themselves. */
  skipAuth?: boolean;
}

function buildHeaders(skipAuth: boolean | undefined, hasJsonBody: boolean): HeadersInit {
  const headers: Record<string, string> = {};
  if (hasJsonBody) headers['Content-Type'] = 'application/json';
  if (!skipAuth) {
    const token = authStore.getAccessToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function rawFetch(path: string, options: RequestOptions): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  try {
    return await fetch(`${API_BASE}${path}`, {
      method: options.method ?? 'GET',
      headers: buildHeaders(options.skipAuth, !options.formData && options.body !== undefined),
      body: options.formData ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError('network', NETWORK_ERROR_MESSAGE);
  } finally {
    clearTimeout(timer);
  }
}

async function toResult<T>(response: Response): Promise<T> {
  const body = await parseJsonBody(response);
  if (!response.ok) {
    const message = extractBackendMessage(body) ?? NETWORK_ERROR_MESSAGE;
    throw new ApiError(errorCodeForStatus(response.status), message);
  }
  return body as T;
}

// A single in-flight refresh is shared by every request that hits a 401
// concurrently, so N simultaneous 401s trigger exactly one POST /auth/refresh
// (see BUILD_PLAN.md Lot 10 — refresh concurrent).
let refreshInFlight: Promise<TokenPair> | null = null;

async function performRefresh(): Promise<TokenPair> {
  const refresh = authStore.getRefreshToken();
  if (!refresh) throw new ApiError('validation', SESSION_EXPIRED_MESSAGE);

  const response = await rawFetch('/auth/refresh', {
    method: 'POST',
    body: { refresh },
    skipAuth: true,
  });
  const tokens = await toResult<TokenPair>(response);
  authStore.setTokens(tokens);
  return tokens;
}

function refreshOnce(): Promise<TokenPair> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/**
 * Typed fetch wrapper for `/api/v1/*`: injects `Authorization: Bearer`,
 * retries exactly once on a 401 after a (deduplicated) silent refresh, and
 * maps the backend's `{ error: { code, message } }` shape to `ApiError`.
 * If the refresh itself fails, the session is purged and callers observe a
 * rejected promise — `AuthProvider` is the one that reacts by redirecting
 * to `/connexion` (it registers via `authStore.onForcedLogout`).
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await rawFetch(path, options);

  if (response.status === 401 && !options.skipAuth) {
    try {
      await refreshOnce();
    } catch {
      authStore.clear();
      authStore.notifyForcedLogout();
      throw new ApiError('validation', SESSION_EXPIRED_MESSAGE);
    }
    const retryResponse = await rawFetch(path, options);
    return toResult<T>(retryResponse);
  }

  return toResult<T>(response);
}
