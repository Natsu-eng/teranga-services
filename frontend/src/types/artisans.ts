/**
 * Artisans : fiche, avis, métiers, statistiques, profil Pro, médias et
 * vérification d'identité.
 */
export interface Review {
  id: string;
  author: string;
  avatarInitials: string;
  rating: number;
  date: string;
  comment: string;
  /**
   * Statut de modération, dit tel quel par le serveur : `signale` = signalé
   * par l'artisan, en attente de décision (toujours visible et compté).
   * Absent sur les données de démonstration.
   */
  moderationStatus?: 'publie' | 'masque' | 'signale';
}

/** Un avis reçu, vu par l'artisan lui-même (masqués compris). */
export interface MyReceivedReview {
  id: string;
  rating: number;
  comment: string;
  authorName: string;
  createdAt: string;
  status: 'publie' | 'masque' | 'signale';
  reportReason: string | null;
  reportedAt: string | null;
  /** Un seul signalement par avis, et seulement sur un avis publié. */
  canReport: boolean;
}

export interface Realisation {
  id: string;
  title: string;
  imageUrl: string;
  altText: string;
}

export interface Trade {
  id: string;
  code: string;
  labelFr: string;
}

export interface Artisan {
  id: string;
  name: string;
  trade: string; // e.g., 'Plomberie', 'Électricité', 'Climatisation'
  avatarUrl: string | null;
  coverUrl: string | null;
  verified: boolean;
  rating: number;
  reviewCount: number;
  distance: string;
  priceBase: string; // e.g. "15.000 CFA"
  priceNumber: number;
  tags: string[];
  /**
   * Codes métier déclarés (ex. « plomberie »), dans le même ordre que `tags`.
   * Nécessaires pour proposer une demande de devis : le serveur refuse de
   * mettre un client en relation avec un artisan qui n'exerce pas le métier
   * de sa demande (ArtisanMetierNonExerce).
   */
  tradeCodes: string[];
  bio: string;
  stats: {
    experience: string; // e.g. "8 ans"
  };
  realisations: Realisation[];
  reviews: Review[];
  available: boolean;
}

/**
 * Mirrors `GET /artisans/{id}/stats` (BUILD_PLAN.md §3.2, §5 Lot 9) exactly —
 * every field is either a real reputation indicator or `null` when the
 * backend has nothing honest to report yet, never an invented number.
 */
export interface ArtisanStats {
  ratingAvg: number | null;
  reviewCount: number;
  interventionsCount: number;
  // Mirrors the backend's `response_rate` verbatim (BUILD_PLAN.md §3.2) —
  // always `null` today: no `responded_at` tracking exists yet in the
  // backend model (Lot 9) to compute a real rate. No unit/scale is assumed
  // here since the backend has never populated it.
  responseRate: number | null;
  // Only present when the caller is the artisan owner or an admin
  // (`ArtisanStatsPrivateOut`) — `null` for the public view, never 0
  // standing in for "not authorized to see this".
  revenueFcfa: number | null;
}

export type ArtisanVerifiedStatus = 'none' | 'pending' | 'verified' | 'rejected';

/**
 * Un métier déclaré par l'artisan lui-même (`POST/DELETE
 * /artisans/me/trades`) — porte l'`id` nécessaire pour le retirer,
 * contrairement aux champs `tags`/`trade` en lecture seule de `Artisan`
 * (vue publique recherche/détail).
 */
export interface ArtisanTradeDetail {
  id: string;
  tradeCode: string;
  tradeLabel: string;
  hourlyRateFcfa: number;
  serviceRadiusM: number;
  hasCustomServiceArea: boolean;
}

/**
 * Le propre profil de l'artisan, tel qu'édité pendant l'onboarding
 * (`PATCH /artisans/me`, `GET /artisans/{id}` en vue de soi-même) — plus
 * riche que `Artisan` (vue publique) : expose chaque métier déclaré avec
 * son propre id/tarif/rayon plutôt qu'un seul libellé `trade` aplati.
 */
export interface MyArtisanProfile {
  id: string;
  fullName: string;
  bio: string | null;
  yearsExperience: number | null;
  avatarUrl: string | null;
  // Photo de couverture (bandeau de la fiche publique) -- même régime
  // public que `avatarUrl`, éditée depuis l'onboarding (lot feat/profile-media).
  coverUrl: string | null;
  isAvailable: boolean;
  verifiedStatus: ArtisanVerifiedStatus;
  trades: ArtisanTradeDetail[];
  /** Suspendu par un admin : invisible en recherche, aucune nouvelle demande. */
  isSuspended: boolean;
  /** Motif de la suspension, montré à l'artisan lui-même (jamais au public). */
  suspensionReason: string | null;
}

/** Limites d'envoi d'une photo du profil, telles qu'appliquées par le serveur. */
export interface MediaUploadLimits {
  maxUploadBytes: number;
  maxSidePx: number;
}

/**
 * `GET /artisans/me/media-constraints` — seule source de vérité des
 * contraintes de photo de profil/couverture (aucun plafond en dur côté front).
 */
export interface ProfileMediaConstraints {
  acceptedMimeTypes: string[];
  maxPixels: number;
  avatar: MediaUploadLimits;
  cover: MediaUploadLimits;
}

export type VerificationDocType = 'cni' | 'selfie' | 'accreditation' | 'address_proof';
export type VerificationDocStatus = 'pending' | 'approved' | 'rejected';

export interface VerificationDocument {
  id: string;
  docType: VerificationDocType;
  status: VerificationDocStatus;
  note: string | null;
  createdAt: string;
  reviewedAt: string | null;
}

export interface MyVerification {
  verifiedStatus: ArtisanVerifiedStatus;
  documents: VerificationDocument[];
}

/** Une ligne de la file d'attente admin (`GET /admin/verifications`). */
export interface AdminVerificationListItem {
  id: string;
  artisanId: string;
  artisanFullName: string;
  docType: VerificationDocType;
  status: VerificationDocStatus;
  note: string | null;
  createdAt: string;
  reviewedAt: string | null;
}

/** Résultat d'une décision admin (`approve`/`reject`) — porte le
 * `verifiedStatus` résultant de l'artisan, recalculé côté serveur. */
export interface AdminVerificationReview {
  id: string;
  docType: VerificationDocType;
  status: VerificationDocStatus;
  note: string | null;
  reviewedBy: string;
  reviewedAt: string;
  artisanId: string;
  artisanVerifiedStatus: ArtisanVerifiedStatus;
}
