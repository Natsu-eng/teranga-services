export type UserRole = 'client' | 'artisan';

export interface Review {
  id: string;
  author: string;
  avatarInitials: string;
  rating: number;
  date: string;
  comment: string;
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
  location: string;
  priceBase: string; // e.g. "15.000 CFA"
  priceNumber: number;
  tags: string[];
  bio: string;
  stats: {
    chantiers: string; // e.g. "150+"
    responseTime: string; // e.g. "< 1h"
    experience: string; // e.g. "8 ans"
  };
  realisations: Realisation[];
  reviews: Review[];
  available: boolean;
}

export interface DevisProposal {
  id: string;
  title: string;
  laborPrice: number; // e.g. 8000
  materialsPrice: number; // e.g. 4000
  totalPrice: number; // e.g. 12000
  currency: string; // "FCFA"
  status: 'pending' | 'accepted' | 'declined';
  date: string;
}

export interface ChatMessage {
  id: string;
  sender: 'client' | 'artisan' | 'system';
  text?: string;
  timestamp: string;
  devis?: DevisProposal;
  photoUrl?: string;
}

export interface JobRequest {
  id: string;
  clientName: string;
  clientAvatar: string;
  title: string;
  trade: string;
  location: string;
  timeAgo: string;
  estimatedPrice: string;
  status: 'new' | 'accepted' | 'completed';
  description?: string;
}

export interface AIAnalysisResult {
  trade: string;
  // Backend trade code (e.g. "plomberie") backing `trade` (its French label) —
  // the value a service_request/artisan search actually filters on, kept
  // alongside the display label instead of forcing callers to reverse-map it.
  tradeCode: string;
  priceEstimate: string;
  // Raw FCFA bounds backing `priceEstimate`'s formatted string — needed to
  // relay the AI's estimate to `POST /requests` (ai_estimate_min/max_fcfa).
  priceMinFcfa: number;
  priceMaxFcfa: number;
  recommendedCount: number;
  explanation: string;
  urgency: string;
  // Backend urgency enum backing `urgency` (its French display label).
  urgencyCode: 'normal' | 'urgent' | 'immediat';
  suggestedDevis: {
    title: string;
    labor: number;
    materials: number;
    total: number;
  };
}

export type ServiceRequestStatus = 'ouverte' | 'en_relation' | 'convertie' | 'annulee' | 'expiree';

export interface ServiceRequest {
  id: string;
  tradeCode: string;
  tradeLabel: string;
  description: string;
  photoUrl: string | null;
  location: { lat: number; lng: number };
  urgency: string;
  aiEstimateMinFcfa: number | null;
  aiEstimateMaxFcfa: number | null;
  status: ServiceRequestStatus;
  createdAt: string;
}

export type InterventionStatus =
  | 'proposee'
  | 'acceptee'
  | 'en_cours'
  | 'terminee'
  | 'annulee'
  | 'litige';

export type QuoteStatus = 'propose' | 'accepte' | 'refuse' | 'expire';

export interface Quote {
  id: string;
  laborFcfa: number;
  materialsFcfa: number;
  totalFcfa: number;
  status: QuoteStatus;
  createdAt: string;
}

export interface Intervention {
  id: string;
  serviceRequest: ServiceRequest;
  clientId: string;
  artisanId: string;
  status: InterventionStatus;
  commissionRateBps: number;
  agreedAmountFcfa: number | null;
  scheduledAt: string | null;
  completedAt: string | null;
  declineReason: string | null;
  quote: Quote | null;
  review: Review | null;
  createdAt: string;
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
  isAvailable: boolean;
  verifiedStatus: ArtisanVerifiedStatus;
  trades: ArtisanTradeDetail[];
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

export interface CurrentUser {
  id: string;
  name: string;
  initials: string;
  verified: boolean;
  // Real artisan_profile.id (from GET /auth/me), null for a client or an
  // artisan account without a profile yet — never a placeholder.
  artisanId: string | null;
}
