/**
 * Demandes des clients : triage IA, demande, éligibilité d'un artisan.
 */
export interface AIAnalysisResult {
  // `null` (avec `tradeCode`) : aucun métier reconnu dans la description --
  // le client le choisit lui-même, jamais un métier imposé par défaut.
  trade: string | null;
  // Backend trade code (e.g. "plomberie") backing `trade` (its French label) —
  // the value a service_request/artisan search actually filters on, kept
  // alongside the display label instead of forcing callers to reverse-map it.
  tradeCode: string | null;
  urgency: string;
  // Backend urgency enum backing `urgency` (its French display label).
  urgencyCode: 'normal' | 'urgent' | 'immediat';
  // Aucune estimation de prix : sans fondement réel (table fixe par métier),
  // elle n'est plus ni affichée ni transmise (prévu : la calculer un jour à
  // partir des devis réellement acceptés).
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
  // L'estimation enregistrée sur les anciennes demandes reste en base mais
  // n'est plus lue : chiffre sans fondement réel, jamais réaffiché.
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
