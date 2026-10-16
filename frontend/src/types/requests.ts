/**
 * Demandes des clients : triage IA, demande, éligibilité d'un artisan.
 */
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
  /** Lieu confirmé par le client (« Dakar Plateau »…) ; null pour les demandes antérieures. */
  locationLabel: string | null;
  urgency: string;
  aiEstimateMinFcfa: number | null;
  aiEstimateMaxFcfa: number | null;
  status: ServiceRequestStatus;
  /** Demande ouverte : date à laquelle elle expirera sans artisan (sinon null). */
  expiresAt: string | null;
  createdAt: string;
}

/**
 * Pourquoi un artisan ne peut pas recevoir une demande — même règle que
 * l'envoi (POST /interventions), lue AVANT d'envoyer.
 */
export type EngagementBlocker = 'artisan_non_verifie' | 'metier_non_exerce' | 'hors_zone';

export interface EngagementCheck {
  eligible: boolean;
  reason: EngagementBlocker | null;
}

export interface RequestEligibility extends EngagementCheck {
  requestId: string;
}
