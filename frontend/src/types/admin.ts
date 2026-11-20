/**
 * Types du back-office admin (BUILD_PLAN.md §3.6), reflets camelCase des
 * schémas `/admin/*` du backend. Chaque chiffre affiché vient du serveur :
 * aucun n'est calculé ni estimé côté interface.
 */
import type { ArtisanVerifiedStatus, VerificationDocStatus, VerificationDocType } from './index';

/** Une page d'une liste paginée côté serveur. */
export interface PageResult<T> {
  items: T[];
  page: number;
  total: number;
  totalPages: number;
}

// ------------------------------------------------------------ vue d'ensemble

export interface AdminOverview {
  artisans: {
    total: number;
    none: number;
    pending: number;
    verified: number;
    rejected: number;
    suspended: number;
  };
  users: { clients: number; artisans: number; admins: number };
  interventions: {
    proposee: number;
    acceptee: number;
    enCours: number;
    terminee: number;
    annulee: number;
    litige: number;
  };
  money: {
    inEscrowFcfa: number;
    releasedFcfa: number;
    cashFcfa: number;
    refundedFcfa: number;
    businessVolumeFcfa: number;
    commissionCollectedFcfa: number;
    commissionDueFcfa: number;
    commissionPendingFcfa: number;
  };
  pendingVerifications: number;
  openDisputes: number;
  reportedReviews: number;
  generatedAt: string;
}

// ------------------------------------------------------------------- journal

export type AuditAction =
  | 'admin.bootstrap'
  | 'verification.approve'
  | 'verification.reject'
  | 'dispute.resolve'
  | 'artisan.suspend'
  | 'artisan.reactivate'
  | 'user.grant_admin'
  | 'user.revoke_admin'
  | 'review.hide'
  | 'review.restore'
  | 'commission_rate.create'
  | 'support_ticket.reply';

export type AuditTargetType =
  | 'verification'
  | 'intervention'
  | 'artisan'
  | 'user'
  | 'review'
  | 'commission_rate'
  | 'support_ticket';

export interface AuditEntry {
  id: string;
  createdAt: string;
  /** `null` : action hors application (script CLI de création du premier admin). */
  actorId: string | null;
  actorName: string | null;
  action: AuditAction;
  targetType: AuditTargetType;
  targetId: string | null;
  /** Détails bruts, tels que journalisés (motif, statut précédent...). */
  details: Record<string, unknown>;
}

export interface AuditFilters {
  action?: AuditAction;
  targetType?: AuditTargetType;
  targetId?: string;
  page?: number;
}

// ------------------------------------------------------------------ artisans

/** Filtre de la liste : un statut de vérification, ou les suspendus. */
export type AdminArtisanStatusFilter = ArtisanVerifiedStatus | 'suspended';

export interface AdminArtisanListItem {
  id: string;
  fullName: string;
  phone: string;
  verifiedStatus: ArtisanVerifiedStatus;
  isSuspended: boolean;
  tradeLabels: string[];
  ratingAvg: number | null;
  reviewCount: number;
  pendingDocuments: number;
  createdAt: string;
}

export interface AdminArtisanDocument {
  id: string;
  docType: VerificationDocType;
  status: VerificationDocStatus;
  note: string | null;
  createdAt: string;
  reviewedAt: string | null;
}

export interface AdminArtisanDetail {
  id: string;
  fullName: string;
  phone: string;
  bio: string | null;
  yearsExperience: number | null;
  avatarUrl: string | null;
  isAvailable: boolean;
  verifiedStatus: ArtisanVerifiedStatus;
  tradeLabels: string[];
  documents: AdminArtisanDocument[];
  createdAt: string;
  ratingAvg: number | null;
  reviewCount: number;
  isSuspended: boolean;
  suspendedAt: string | null;
  suspensionReason: string | null;
  /** Interventions par statut (clés du backend : `proposee`, `en_cours`...). */
  interventions: Record<string, number>;
  /** Décisions admin le concernant, plus récentes d'abord. */
  history: AuditEntry[];
}

export interface AdminArtisanFilters {
  status?: AdminArtisanStatusFilter;
  q?: string;
  page?: number;
}

// ------------------------------------------------------------- utilisateurs

export type AccountRole = 'client' | 'artisan' | 'admin';

export interface AdminUser {
  id: string;
  fullName: string;
  phone: string;
  role: AccountRole;
  createdAt: string;
  hasArtisanProfile: boolean;
  isSelf: boolean;
  canGrantAdmin: boolean;
  canRevokeAdmin: boolean;
  /** Pourquoi l'action n'est pas possible (affiché AVANT toute tentative). */
  guard: string | null;
}

export interface AdminUserFilters {
  role?: AccountRole;
  q?: string;
  page?: number;
}

// --------------------------------------------------------------------- avis

export type ReviewModerationStatus = 'publie' | 'masque' | 'signale';

export interface AdminReview {
  id: string;
  rating: number;
  comment: string;
  status: ReviewModerationStatus;
  contactVerified: boolean;
  createdAt: string;
  interventionId: string;
  authorId: string;
  /** Nom RÉEL de l'auteur (l'admin en a besoin pour juger). */
  authorName: string;
  artisanId: string;
  artisanName: string;
  reportReason: string | null;
  reportedAt: string | null;
}

export interface AdminReviewFilters {
  status?: ReviewModerationStatus;
  artisanId?: string;
  q?: string;
  page?: number;
}

// --------------------------------------------------------------- commissions

export type CommissionRateState = 'en_vigueur' | 'programme' | 'archive';

export interface CommissionRate {
  id: string;
  rateBps: number;
  /** `null` : taux global (tous métiers sans taux propre). */
  tradeCode: string | null;
  tradeLabel: string | null;
  effectiveFrom: string;
  effectiveTo: string | null;
  state: CommissionRateState;
  /** Interventions qui ont FIGÉ ce taux à leur création. */
  interventionsCount: number;
  createdAt: string;
}

export interface CommissionGrid {
  items: CommissionRate[];
  /** Plafond de saisie configuré côté serveur (garde-fou). */
  maxRateBps: number;
  generatedAt: string;
}

export interface AddCommissionRateInput {
  rateBps: number;
  /** Absent : taux global. */
  tradeCode?: string | null;
  /** Absent : maintenant. ISO 8601 avec fuseau. */
  effectiveFrom?: string | null;
  note?: string | null;
}
