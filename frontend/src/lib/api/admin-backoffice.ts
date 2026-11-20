/**
 * Accès HTTP du back-office admin (BUILD_PLAN.md §3.6) : vue d'ensemble,
 * artisans, utilisateurs, avis, grille de commission, journal d'audit.
 *
 * Module séparé de `http-impl.ts` pour rester lisible ; il est fusionné dans
 * `httpApiClient` et son contrat (`AdminBackofficeApi`) fait partie
 * d'`ApiClient` : un oubli d'implémentation reste une erreur de compilation.
 * Les règles (anti-verrouillage, motif obligatoire, taux jamais modifiés)
 * sont TOUJOURS appliquées par le serveur ; l'interface les affiche, elle ne
 * les remplace pas.
 */
import type {
  AddCommissionRateInput,
  AdminArtisanDetail,
  AdminArtisanFilters,
  AdminArtisanListItem,
  AdminOverview,
  AdminReview,
  AdminReviewFilters,
  AdminUser,
  AdminUserFilters,
  AuditEntry,
  AuditFilters,
  CommissionGrid,
  CommissionRate,
  PageResult,
} from '../../types/admin';
import type { AdminSupportFilters, AdminSupportTicket } from '../../types/support';
import type { BackendAdminSupportTicket } from './backend-types';
import { apiRequest } from './http';
import { mapAdminSupportTicket } from './mappers';
import type {
  BackendAdminArtisanDetail,
  BackendAdminArtisanListItem,
  BackendAdminReview,
  BackendAdminUser,
  BackendAuditEntry,
  BackendCommissionGrid,
  BackendCommissionRate,
  BackendOverview,
  BackendPage,
} from './admin-backoffice-mappers';
import {
  mapArtisanDetail,
  mapArtisanListItem,
  mapAuditEntry,
  mapOverview,
  mapPage,
  mapRate,
  mapReview,
  mapUser,
} from './admin-backoffice-mappers';

export interface AdminBackofficeApi {
  getAdminOverview(): Promise<AdminOverview>;
  listAdminArtisans(filters?: AdminArtisanFilters): Promise<PageResult<AdminArtisanListItem>>;
  getAdminArtisan(artisanId: string): Promise<AdminArtisanDetail>;
  suspendArtisan(artisanId: string, reason: string): Promise<AdminArtisanDetail>;
  reactivateArtisan(artisanId: string, note?: string | null): Promise<AdminArtisanDetail>;
  listAdminUsers(filters?: AdminUserFilters): Promise<PageResult<AdminUser>>;
  grantAdmin(userId: string, note?: string | null): Promise<AdminUser>;
  revokeAdmin(userId: string, note?: string | null): Promise<AdminUser>;
  listAdminReviews(filters?: AdminReviewFilters): Promise<PageResult<AdminReview>>;
  hideReview(reviewId: string, reason: string): Promise<AdminReview>;
  restoreReview(reviewId: string, note?: string | null): Promise<AdminReview>;
  getCommissionGrid(): Promise<CommissionGrid>;
  addCommissionRate(input: AddCommissionRateInput): Promise<CommissionRate>;
  listAuditEntries(filters?: AuditFilters): Promise<PageResult<AuditEntry>>;
  /** Aide : file des demandes (ouvertes par défaut, la plus ancienne d'abord). */
  listAdminSupportTickets(filters?: AdminSupportFilters): Promise<PageResult<AdminSupportTicket>>;
  /** Répond à une demande, et la clôt si `resolve`. Journalisé par le serveur. */
  replySupportTicket(
    ticketId: string,
    reply: string,
    resolve: boolean,
  ): Promise<AdminSupportTicket>;
}

/** Paramètres de requête, sans les valeurs absentes ni les chaînes vides. */
function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    const text = String(value).trim();
    if (text) search.set(key, text);
  }
  const result = search.toString();
  return result ? `?${result}` : '';
}

// ------------------------------------------------------------ implémentation

export const httpAdminBackoffice: AdminBackofficeApi = {
  async getAdminOverview() {
    return mapOverview(await apiRequest<BackendOverview>('/admin/overview'));
  },

  async listAdminArtisans(filters) {
    const page = await apiRequest<BackendPage<BackendAdminArtisanListItem>>(
      `/admin/artisans${query({ status: filters?.status, q: filters?.q, page: filters?.page })}`,
    );
    return mapPage(page, mapArtisanListItem);
  },

  async getAdminArtisan(artisanId) {
    return mapArtisanDetail(
      await apiRequest<BackendAdminArtisanDetail>(`/admin/artisans/${artisanId}`),
    );
  },

  async suspendArtisan(artisanId, reason) {
    return mapArtisanDetail(
      await apiRequest<BackendAdminArtisanDetail>(`/admin/artisans/${artisanId}/suspend`, {
        method: 'POST',
        body: { reason },
      }),
    );
  },

  async reactivateArtisan(artisanId, note) {
    return mapArtisanDetail(
      await apiRequest<BackendAdminArtisanDetail>(`/admin/artisans/${artisanId}/reactivate`, {
        method: 'POST',
        body: { note: note || null },
      }),
    );
  },

  async listAdminUsers(filters) {
    const page = await apiRequest<BackendPage<BackendAdminUser>>(
      `/admin/users${query({ role: filters?.role, q: filters?.q, page: filters?.page })}`,
    );
    return mapPage(page, mapUser);
  },

  async grantAdmin(userId, note) {
    return mapUser(
      await apiRequest<BackendAdminUser>(`/admin/users/${userId}/grant-admin`, {
        method: 'POST',
        body: { note: note || null },
      }),
    );
  },

  async revokeAdmin(userId, note) {
    return mapUser(
      await apiRequest<BackendAdminUser>(`/admin/users/${userId}/revoke-admin`, {
        method: 'POST',
        body: { note: note || null },
      }),
    );
  },

  async listAdminReviews(filters) {
    const page = await apiRequest<BackendPage<BackendAdminReview>>(
      `/admin/reviews${query({
        status: filters?.status,
        artisan_id: filters?.artisanId,
        q: filters?.q,
        page: filters?.page,
      })}`,
    );
    return mapPage(page, mapReview);
  },

  async hideReview(reviewId, reason) {
    return mapReview(
      await apiRequest<BackendAdminReview>(`/admin/reviews/${reviewId}/hide`, {
        method: 'POST',
        body: { reason },
      }),
    );
  },

  async restoreReview(reviewId, note) {
    return mapReview(
      await apiRequest<BackendAdminReview>(`/admin/reviews/${reviewId}/restore`, {
        method: 'POST',
        body: { note: note || null },
      }),
    );
  },

  async getCommissionGrid() {
    const grid = await apiRequest<BackendCommissionGrid>('/admin/commission-rates');
    return {
      items: grid.items.map(mapRate),
      maxRateBps: grid.max_rate_bps,
      generatedAt: grid.generated_at,
    };
  },

  async addCommissionRate(input) {
    return mapRate(
      await apiRequest<BackendCommissionRate>('/admin/commission-rates', {
        method: 'POST',
        body: {
          rate_bps: input.rateBps,
          trade_code: input.tradeCode || null,
          effective_from: input.effectiveFrom || null,
          note: input.note || null,
        },
      }),
    );
  },

  async listAuditEntries(filters) {
    const page = await apiRequest<BackendPage<BackendAuditEntry>>(
      `/admin/audit${query({
        action: filters?.action,
        target_type: filters?.targetType,
        target_id: filters?.targetId,
        page: filters?.page,
      })}`,
    );
    return mapPage(page, mapAuditEntry);
  },

  async listAdminSupportTickets(filters) {
    const page = await apiRequest<BackendPage<BackendAdminSupportTicket>>(
      `/admin/support/tickets${query({ status: filters?.status, page: filters?.page })}`,
    );
    return mapPage(page, mapAdminSupportTicket);
  },

  async replySupportTicket(ticketId, reply, resolve) {
    return mapAdminSupportTicket(
      await apiRequest<BackendAdminSupportTicket>(`/admin/support/tickets/${ticketId}/reply`, {
        method: 'POST',
        body: { reply, resolve },
      }),
    );
  },
};
