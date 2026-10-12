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
import type {
  ArtisanVerifiedStatus,
  VerificationDocStatus,
  VerificationDocType,
} from '../../types';
import { apiRequest } from './http';

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
}

// ------------------------------------------------------------ formes backend

interface BackendPage<T> {
  items: T[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

interface BackendOverview {
  artisans: AdminOverview['artisans'];
  users: AdminOverview['users'];
  interventions: {
    proposee: number;
    acceptee: number;
    en_cours: number;
    terminee: number;
    annulee: number;
    litige: number;
  };
  money: {
    in_escrow_fcfa: number;
    released_fcfa: number;
    cash_fcfa: number;
    refunded_fcfa: number;
    business_volume_fcfa: number;
    commission_collected_fcfa: number;
    commission_due_fcfa: number;
    commission_pending_fcfa: number;
  };
  pending_verifications: number;
  open_disputes: number;
  reported_reviews: number;
  generated_at: string;
}

interface BackendAuditEntry {
  id: string;
  created_at: string;
  actor_id: string | null;
  actor_name: string | null;
  action: AuditEntry['action'];
  target_type: AuditEntry['targetType'];
  target_id: string | null;
  details: Record<string, unknown>;
}

interface BackendAdminArtisanListItem {
  id: string;
  full_name: string;
  phone: string;
  verified_status: ArtisanVerifiedStatus;
  is_suspended: boolean;
  trade_labels: string[];
  rating_avg: number | null;
  review_count: number;
  pending_documents: number;
  created_at: string;
}

interface BackendAdminArtisanDetail {
  id: string;
  full_name: string;
  phone: string;
  bio: string | null;
  years_experience: number | null;
  avatar_url: string | null;
  is_available: boolean;
  verified_status: ArtisanVerifiedStatus;
  trades: { trade: { label_fr: string } }[];
  documents: {
    id: string;
    doc_type: VerificationDocType;
    status: VerificationDocStatus;
    note: string | null;
    created_at: string;
    reviewed_at: string | null;
  }[];
  created_at: string;
  rating_avg: number | null;
  review_count: number;
  is_suspended: boolean;
  suspended_at: string | null;
  suspension_reason: string | null;
  interventions: Record<string, number>;
  history: BackendAuditEntry[];
}

interface BackendAdminUser {
  id: string;
  full_name: string;
  phone: string;
  role: AdminUser['role'];
  created_at: string;
  has_artisan_profile: boolean;
  is_self: boolean;
  can_grant_admin: boolean;
  can_revoke_admin: boolean;
  guard: string | null;
}

interface BackendAdminReview {
  id: string;
  rating: number;
  comment: string;
  status: AdminReview['status'];
  contact_verified: boolean;
  created_at: string;
  intervention_id: string;
  author_id: string;
  author_name: string;
  artisan_id: string;
  artisan_name: string;
  report_reason: string | null;
  reported_at: string | null;
}

interface BackendCommissionRate {
  id: string;
  rate_bps: number;
  trade_code: string | null;
  trade_label: string | null;
  effective_from: string;
  effective_to: string | null;
  state: CommissionRate['state'];
  interventions_count: number;
  created_at: string;
}

interface BackendCommissionGrid {
  items: BackendCommissionRate[];
  max_rate_bps: number;
  generated_at: string;
}

// ------------------------------------------------------------------ mappeurs

function mapPage<B, T>(page: BackendPage<B>, map: (item: B) => T): PageResult<T> {
  return {
    items: page.items.map(map),
    page: page.pagination.page,
    total: page.pagination.total,
    totalPages: page.pagination.total_pages,
  };
}

function mapOverview(o: BackendOverview): AdminOverview {
  return {
    artisans: o.artisans,
    users: o.users,
    interventions: {
      proposee: o.interventions.proposee,
      acceptee: o.interventions.acceptee,
      enCours: o.interventions.en_cours,
      terminee: o.interventions.terminee,
      annulee: o.interventions.annulee,
      litige: o.interventions.litige,
    },
    money: {
      inEscrowFcfa: o.money.in_escrow_fcfa,
      releasedFcfa: o.money.released_fcfa,
      cashFcfa: o.money.cash_fcfa,
      refundedFcfa: o.money.refunded_fcfa,
      businessVolumeFcfa: o.money.business_volume_fcfa,
      commissionCollectedFcfa: o.money.commission_collected_fcfa,
      commissionDueFcfa: o.money.commission_due_fcfa,
      commissionPendingFcfa: o.money.commission_pending_fcfa,
    },
    pendingVerifications: o.pending_verifications,
    openDisputes: o.open_disputes,
    reportedReviews: o.reported_reviews,
    generatedAt: o.generated_at,
  };
}

export function mapAuditEntry(e: BackendAuditEntry): AuditEntry {
  return {
    id: e.id,
    createdAt: e.created_at,
    actorId: e.actor_id,
    actorName: e.actor_name,
    action: e.action,
    targetType: e.target_type,
    targetId: e.target_id,
    details: e.details,
  };
}

function mapArtisanListItem(a: BackendAdminArtisanListItem): AdminArtisanListItem {
  return {
    id: a.id,
    fullName: a.full_name,
    phone: a.phone,
    verifiedStatus: a.verified_status,
    isSuspended: a.is_suspended,
    tradeLabels: a.trade_labels,
    ratingAvg: a.rating_avg,
    reviewCount: a.review_count,
    pendingDocuments: a.pending_documents,
    createdAt: a.created_at,
  };
}

function mapArtisanDetail(a: BackendAdminArtisanDetail): AdminArtisanDetail {
  return {
    id: a.id,
    fullName: a.full_name,
    phone: a.phone,
    bio: a.bio,
    yearsExperience: a.years_experience,
    avatarUrl: a.avatar_url,
    isAvailable: a.is_available,
    verifiedStatus: a.verified_status,
    tradeLabels: a.trades.map((t) => t.trade.label_fr),
    documents: a.documents.map((d) => ({
      id: d.id,
      docType: d.doc_type,
      status: d.status,
      note: d.note,
      createdAt: d.created_at,
      reviewedAt: d.reviewed_at,
    })),
    createdAt: a.created_at,
    ratingAvg: a.rating_avg,
    reviewCount: a.review_count,
    isSuspended: a.is_suspended,
    suspendedAt: a.suspended_at,
    suspensionReason: a.suspension_reason,
    interventions: a.interventions,
    history: a.history.map(mapAuditEntry),
  };
}

function mapUser(u: BackendAdminUser): AdminUser {
  return {
    id: u.id,
    fullName: u.full_name,
    phone: u.phone,
    role: u.role,
    createdAt: u.created_at,
    hasArtisanProfile: u.has_artisan_profile,
    isSelf: u.is_self,
    canGrantAdmin: u.can_grant_admin,
    canRevokeAdmin: u.can_revoke_admin,
    guard: u.guard,
  };
}

function mapReview(r: BackendAdminReview): AdminReview {
  return {
    id: r.id,
    rating: r.rating,
    comment: r.comment,
    status: r.status,
    contactVerified: r.contact_verified,
    createdAt: r.created_at,
    interventionId: r.intervention_id,
    authorId: r.author_id,
    authorName: r.author_name,
    artisanId: r.artisan_id,
    artisanName: r.artisan_name,
    reportReason: r.report_reason,
    reportedAt: r.reported_at,
  };
}

function mapRate(r: BackendCommissionRate): CommissionRate {
  return {
    id: r.id,
    rateBps: r.rate_bps,
    tradeCode: r.trade_code,
    tradeLabel: r.trade_label,
    effectiveFrom: r.effective_from,
    effectiveTo: r.effective_to,
    state: r.state,
    interventionsCount: r.interventions_count,
    createdAt: r.created_at,
  };
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
};
