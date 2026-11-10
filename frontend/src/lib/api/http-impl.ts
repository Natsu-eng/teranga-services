/**
 * Implémentation HTTP — et seule implémentation de production — de
 * `ApiClient`, adossée au backend FastAPI. Couvre le contrat EN ENTIER
 * (typé `ApiClient`, pas un sous-ensemble) : voir index.ts.
 *
 * Schema adaptation: the backend's artisan schemas (`app/schemas/artisans.py`)
 * intentionally omit any contact field (phone/email — anti-disintermediation,
 * BUILD_PLAN.md Lot 9) and don't carry several fields the mock UI model
 * invented (a public hourly price, a human-readable "location", a weekly
 * revenue breakdown...). Rather than fabricate values, missing fields map to
 * neutral, honest placeholders (see `mapArtisan` below) — never an invented
 * number or address.
 */
import type {
  AdminVerificationListItem,
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  MessageHistory,
  AdminVerificationReview,
  AIAnalysisResult,
  Artisan,
  ArtisanStats,
  ArtisanEarnings,
  ClientPayment,
  EngagementBlocker,
  EngagementCheck,
  RequestEligibility,
  Intervention,
  MyArtisanProfile,
  MyReceivedReview,
  PaymentChannel,
  PaymentOptions,
  PaymentSummary,
  PayoutChannel,
  PayoutSettings,
  MyVerification,
  ProfileMediaConstraints,
  Review,
  ServiceRequest,
  Trade,
  VerificationDocType,
  VerificationDocument,
} from '../../types';
import { apiRequest, apiRequestBlob } from './http';
import { httpAdminBackoffice } from './admin-backoffice';
import { ApiError } from './types';
import type {
  AddArtisanTradeInput,
  AdminVerificationFilters,
  ApiClient,
  ArtisanFilters,
  ConversationFilters,
  CreateInterventionInput,
  CreateQuoteInput,
  MessageCursor,
  RealtimeTicket,
  CreateReviewInput,
  CreateServiceRequestInput,
  UpdateArtisanProfileInput,
} from './types';
import type {
  BackendAdminVerificationListItem,
  BackendAdminVerificationReview,
  BackendArtisanDetail,
  BackendArtisanListItem,
  BackendArtisanStats,
  BackendChatMessage,
  BackendClientPayment,
  BackendConversation,
  BackendConversationSummary,
  BackendEarnings,
  BackendIntervention,
  BackendMyReceivedReview,
  BackendMyVerification,
  BackendPage,
  BackendPaymentSummary,
  BackendPayoutSettings,
  BackendProfileMediaConstraints,
  BackendReview,
  BackendServiceRequest,
  BackendTrade,
  BackendTriageResult,
  BackendVerificationDocument,
} from './backend-types';
import {
  URGENCY_LABELS,
  mapAdminVerificationListItem,
  mapAdminVerificationReview,
  mapArtisan,
  mapArtisanStats,
  mapChatMessage,
  mapConversation,
  mapConversationSummary,
  mapIntervention,
  mapMyArtisanProfile,
  mapMyReceivedReview,
  mapMyVerification,
  mapPaymentSummary,
  mapPayoutSettings,
  mapProfileMediaConstraints,
  mapReview,
  mapServiceRequest,
  mapTrade,
  mapVerificationDocument,
} from './mappers';

const REVIEWS_PAGE_SIZE = 20;
// Avis reçus affichés dans l'espace Pro (plafond serveur : PAGINATION_PAGE_SIZE_MAX).
const MY_REVIEWS_PAGE_SIZE = 50;

function buildArtisanQuery(filters?: ArtisanFilters): string {
  const params = new URLSearchParams();
  if (filters?.trade) params.set('trade', filters.trade);
  if (filters?.search) params.set('q', filters.search);
  if (typeof filters?.minRating === 'number') params.set('min_rating', String(filters.minRating));
  if (filters?.near) params.set('near', `${filters.near.lat},${filters.near.lng}`);
  if (typeof filters?.radiusM === 'number') params.set('radius_m', String(filters.radiusM));
  if (typeof filters?.available === 'boolean') params.set('available', String(filters.available));
  if (filters?.sort) params.set('sort', filters.sort);
  if (typeof filters?.page === 'number') params.set('page', String(filters.page));
  if (typeof filters?.pageSize === 'number') params.set('page_size', String(filters.pageSize));
  const query = params.toString();
  return query ? `?${query}` : '';
}

async function fetchArtisanReviews(artisanId: string): Promise<Review[]> {
  const page = await apiRequest<BackendPage<BackendReview>>(
    `/artisans/${artisanId}/reviews?page=1&page_size=${REVIEWS_PAGE_SIZE}`,
  );
  return page.items.map(mapReview);
}

/**
 * À utiliser pour toute méthode d'`ApiClient` déclarée avant que le backend
 * ne la serve : échoue explicitement avec un code dédié (`not_implemented`)
 * et un message affichable, au lieu de renvoyer des données inventées.
 */
export function notImplemented(feature: string): never {
  throw new ApiError(
    'not_implemented',
    `${feature} n'est pas encore disponible. Merci de réessayer plus tard.`,
  );
}

export const httpApiClient: ApiClient = {
  ...httpAdminBackoffice,

  async listArtisans(filters?: ArtisanFilters): Promise<Artisan[]> {
    const page = await apiRequest<BackendPage<BackendArtisanListItem>>(
      `/artisans${buildArtisanQuery(filters)}`,
    );
    return page.items.map((item) => mapArtisan(item, []));
  },

  async getArtisanById(id: string): Promise<Artisan> {
    // A 404 here already carries the backend's own French, display-ready
    // message (BUILD_PLAN.md §3.1) — propagated as-is by apiRequest, not
    // rewritten here.
    const detail = await apiRequest<BackendArtisanDetail>(`/artisans/${id}`);
    const reviews = await fetchArtisanReviews(id);
    return mapArtisan(detail, reviews);
  },

  async getArtisanStats(artisanId: string): Promise<ArtisanStats> {
    const stats = await apiRequest<BackendArtisanStats>(`/artisans/${artisanId}/stats`);
    return mapArtisanStats(stats);
  },

  async updateArtisanAvailability(isAvailable: boolean): Promise<Artisan> {
    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me', {
      method: 'PATCH',
      body: { is_available: isAvailable },
    });
    return mapArtisan(detail, []);
  },

  async getMyArtisanProfile(artisanId: string): Promise<MyArtisanProfile> {
    const detail = await apiRequest<BackendArtisanDetail>(`/artisans/${artisanId}`);
    return mapMyArtisanProfile(detail);
  },

  async updateMyArtisanProfile(input: UpdateArtisanProfileInput): Promise<MyArtisanProfile> {
    // Seuls les champs réellement fournis par l'appelant sont envoyés --
    // reflète la sémantique de mise à jour partielle du backend
    // (`exclude_unset`, app/schemas/artisans.py ArtisanProfileUpdateIn) :
    // omettre un champ ici ne doit jamais être interprété comme "l'effacer"
    // côté serveur.
    const body: Record<string, unknown> = {};
    if (input.fullName !== undefined) body.full_name = input.fullName;
    if (input.bio !== undefined) body.bio = input.bio;
    if (input.yearsExperience !== undefined) body.years_experience = input.yearsExperience;
    if (input.baseLocation !== undefined) body.base_location = input.baseLocation;
    if (input.avatarUrl !== undefined) body.avatar_url = input.avatarUrl;
    if (input.coverUrl !== undefined) body.cover_url = input.coverUrl;
    if (input.isAvailable !== undefined) body.is_available = input.isAvailable;

    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me', {
      method: 'PATCH',
      body,
    });
    return mapMyArtisanProfile(detail);
  },

  async uploadAvatar(file: File): Promise<MyArtisanProfile> {
    const formData = new FormData();
    formData.set('file', file);
    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me/avatar', {
      method: 'POST',
      formData,
    });
    return mapMyArtisanProfile(detail);
  },

  // Même contrat que uploadAvatar (multipart `file`, profil complet en
  // retour) -- budget d'envois partagé avec l'avatar côté serveur : un 429
  // remonte avec le message français du backend, affiché tel quel.
  async uploadCover(file: File): Promise<MyArtisanProfile> {
    const formData = new FormData();
    formData.set('file', file);
    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me/cover', {
      method: 'POST',
      formData,
    });
    return mapMyArtisanProfile(detail);
  },

  async getProfileMediaConstraints(): Promise<ProfileMediaConstraints> {
    const body = await apiRequest<BackendProfileMediaConstraints>('/artisans/me/media-constraints');
    return mapProfileMediaConstraints(body);
  },

  async addArtisanTrade(input: AddArtisanTradeInput): Promise<MyArtisanProfile> {
    const detail = await apiRequest<BackendArtisanDetail>('/artisans/me/trades', {
      method: 'POST',
      body: {
        trade_code: input.tradeCode,
        hourly_rate_fcfa: input.hourlyRateFcfa,
        service_radius_m: input.serviceRadiusM,
      },
    });
    return mapMyArtisanProfile(detail);
  },

  async removeArtisanTrade(artisanTradeId: string): Promise<MyArtisanProfile> {
    const detail = await apiRequest<BackendArtisanDetail>(`/artisans/me/trades/${artisanTradeId}`, {
      method: 'DELETE',
    });
    return mapMyArtisanProfile(detail);
  },

  async listMyVerificationDocuments(): Promise<MyVerification> {
    const body = await apiRequest<BackendMyVerification>('/artisans/me/documents');
    return mapMyVerification(body);
  },

  async uploadVerificationDocument(
    docType: VerificationDocType,
    file: File,
  ): Promise<VerificationDocument> {
    const formData = new FormData();
    formData.set('doc_type', docType);
    formData.set('file', file);
    const document = await apiRequest<BackendVerificationDocument>('/artisans/me/documents', {
      method: 'POST',
      formData,
    });
    return mapVerificationDocument(document);
  },

  async listAdminVerifications(
    filters?: AdminVerificationFilters,
  ): Promise<AdminVerificationListItem[]> {
    const params = new URLSearchParams();
    if (filters?.status) params.set('status', filters.status);
    // Grande page unique plutôt qu'une pagination -- une file d'attente de
    // revue admin (BUILD_PLAN.md) n'est pas censée accumuler des centaines
    // d'éléments en attente ; si ça arrivait un jour, ce serait un signal
    // opérationnel à traiter avant d'ajouter une UI de pagination.
    params.set('page_size', '100');
    const page = await apiRequest<BackendPage<BackendAdminVerificationListItem>>(
      `/admin/verifications?${params.toString()}`,
    );
    return page.items.map(mapAdminVerificationListItem);
  },

  async getAdminVerificationDocumentBlob(verificationId: string): Promise<Blob> {
    return apiRequestBlob(`/admin/verifications/${verificationId}/content`);
  },

  async approveVerification(verificationId: string): Promise<AdminVerificationReview> {
    const review = await apiRequest<BackendAdminVerificationReview>(
      `/admin/verifications/${verificationId}/approve`,
      { method: 'POST' },
    );
    return mapAdminVerificationReview(review);
  },

  async rejectVerification(verificationId: string, note: string): Promise<AdminVerificationReview> {
    const review = await apiRequest<BackendAdminVerificationReview>(
      `/admin/verifications/${verificationId}/reject`,
      { method: 'POST', body: { note } },
    );
    return mapAdminVerificationReview(review);
  },

  async listTrades(): Promise<Trade[]> {
    const trades = await apiRequest<BackendTrade[]>('/trades');
    return trades.map(mapTrade);
  },

  // Migration of the old Express /api/analyze-problem (Lot 11, BUILD_PLAN.md
  // SS3.2, SS6): the backend now validates the AI output strictly (schema,
  // amounts, trade_code existence) and always falls back to a heuristic
  // rather than erroring, so this call never needs its own try/catch beyond
  // what apiRequest already provides.
  async analyzeProblem(description: string): Promise<AIAnalysisResult> {
    const [result, trades] = await Promise.all([
      apiRequest<BackendTriageResult>('/ai/analyze', {
        method: 'POST',
        body: { description },
      }),
      apiRequest<BackendTrade[]>('/trades').then((list) => list.map(mapTrade)),
    ]);

    // trade_code is guaranteed to reference an active trade by the backend
    // (app.services.ai_triage) -- falling back to the raw code here only
    // guards against a race with a trade deactivated between the two calls.
    const tradeLabel =
      trades.find((t) => t.code === result.trade_code)?.labelFr ?? result.trade_code;

    return {
      trade: tradeLabel,
      tradeCode: result.trade_code,
      // Ni montant (table fixe par métier côté serveur, sans fondement réel),
      // ni phrase d'explication inventée : seulement le métier et l'urgence.
      urgency: URGENCY_LABELS[result.urgency],
      urgencyCode: result.urgency,
    };
  },

  async createServiceRequest(input: CreateServiceRequestInput): Promise<ServiceRequest> {
    const request = await apiRequest<BackendServiceRequest>('/requests', {
      method: 'POST',
      body: {
        trade_code: input.tradeCode,
        description: input.description,
        photo_url: input.photoUrl ?? null,
        location: input.location,
        location_label: input.locationLabel,
        urgency: input.urgency,
      },
    });
    return mapServiceRequest(request);
  },

  async listMyServiceRequests(): Promise<ServiceRequest[]> {
    const page = await apiRequest<BackendPage<BackendServiceRequest>>('/requests/me');
    return page.items.map(mapServiceRequest);
  },

  async cancelServiceRequest(requestId: string): Promise<ServiceRequest> {
    const request = await apiRequest<BackendServiceRequest>(
      `/requests/${encodeURIComponent(requestId)}/cancel`,
      { method: 'POST' },
    );
    return mapServiceRequest(request);
  },

  async listRequestEligibility(artisanId: string): Promise<RequestEligibility[]> {
    const items = await apiRequest<
      { request_id: string; eligible: boolean; reason: EngagementBlocker | null }[]
    >(`/requests/me/eligibility?artisan_id=${encodeURIComponent(artisanId)}`);
    return items.map((item) => ({
      requestId: item.request_id,
      eligible: item.eligible,
      reason: item.reason,
    }));
  },

  async checkArtisanCoverage(
    artisanId: string,
    tradeCode: string,
    location: { lat: number; lng: number },
  ): Promise<EngagementCheck> {
    const params = new URLSearchParams({
      trade: tradeCode,
      lat: String(location.lat),
      lng: String(location.lng),
    });
    return apiRequest<EngagementCheck>(
      `/artisans/${encodeURIComponent(artisanId)}/coverage?${params.toString()}`,
    );
  },

  async listMyInterventions(): Promise<Intervention[]> {
    const page = await apiRequest<BackendPage<BackendIntervention>>('/interventions/me');
    return page.items.map(mapIntervention);
  },

  /**
   * Mise en relation : propose une demande ouverte du client à un artisan
   * (`POST /interventions`). Le serveur vérifie tout — demande ouverte et
   * appartenant au client, artisan vérifié, métier exercé, zone couverte —
   * et renvoie un message affichable en cas de refus.
   */
  async createIntervention(input: CreateInterventionInput): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>('/interventions', {
      method: 'POST',
      body: { service_request_id: input.serviceRequestId, artisan_id: input.artisanId },
    });
    return mapIntervention(intervention);
  },

  async getInterventionById(id: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}`);
    return mapIntervention(intervention);
  },

  async acceptIntervention(id: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/accept`, {
      method: 'POST',
    });
    return mapIntervention(intervention);
  },

  async declineIntervention(id: string, reason?: string | null): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/decline`, {
      method: 'POST',
      body: { reason: reason ?? null },
    });
    return mapIntervention(intervention);
  },

  async createQuote(interventionId: string, input: CreateQuoteInput): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(
      `/interventions/${interventionId}/quote`,
      {
        method: 'POST',
        body: { labor_fcfa: input.laborFcfa, materials_fcfa: input.materialsFcfa },
      },
    );
    return mapIntervention(intervention);
  },

  async acceptQuote(interventionId: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(
      `/interventions/${interventionId}/quote/accept`,
      { method: 'POST' },
    );
    return mapIntervention(intervention);
  },

  async refuseQuote(interventionId: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(
      `/interventions/${interventionId}/quote/refuse`,
      { method: 'POST' },
    );
    return mapIntervention(intervention);
  },

  async completeIntervention(id: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/complete`, {
      method: 'POST',
    });
    return mapIntervention(intervention);
  },

  async cancelIntervention(id: string, reason?: string | null): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/cancel`, {
      method: 'POST',
      body: { reason: reason ?? null },
    });
    return mapIntervention(intervention);
  },

  async openDispute(id: string, reason: string): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(`/interventions/${id}/dispute`, {
      method: 'POST',
      body: { reason },
    });
    return mapIntervention(intervention);
  },

  async createReview(interventionId: string, input: CreateReviewInput): Promise<Review> {
    const review = await apiRequest<BackendReview>(`/interventions/${interventionId}/review`, {
      method: 'POST',
      body: { rating: input.rating, comment: input.comment },
    });
    return mapReview(review);
  },

  // ------------------------------------------------------------- Messagerie

  async listConversations(filters?: ConversationFilters): Promise<ConversationSummary[]> {
    const params = new URLSearchParams({ page_size: '50' });
    if (filters?.artisanId) params.set('artisan_id', filters.artisanId);
    const page = await apiRequest<BackendPage<BackendConversationSummary>>(
      `/conversations/me?${params.toString()}`,
    );
    return page.items.map(mapConversationSummary);
  },

  async getUnreadMessageCount(): Promise<number> {
    const result = await apiRequest<{ count: number }>('/conversations/me/unread-count');
    return result.count;
  },

  async getConversation(conversationId: string): Promise<ConversationDetail> {
    return mapConversation(
      await apiRequest<BackendConversation>(`/conversations/${conversationId}`),
    );
  },

  async listMessages(conversationId: string, cursor?: MessageCursor): Promise<MessageHistory> {
    const params = new URLSearchParams();
    if (cursor?.before !== undefined) params.set('before', String(cursor.before));
    if (cursor?.since !== undefined) params.set('since', String(cursor.since));
    if (cursor?.limit !== undefined) params.set('limit', String(cursor.limit));
    const query = params.toString();
    const history = await apiRequest<{ items: BackendChatMessage[]; has_more: boolean }>(
      `/conversations/${conversationId}/messages${query ? `?${query}` : ''}`,
    );
    return { items: history.items.map(mapChatMessage), hasMore: history.has_more };
  },

  async sendMessage(conversationId: string, body: string): Promise<ChatMessage> {
    return mapChatMessage(
      await apiRequest<BackendChatMessage>(`/conversations/${conversationId}/messages`, {
        method: 'POST',
        body: { body },
      }),
    );
  },

  async sendImageMessage(
    conversationId: string,
    file: File,
    caption: string,
  ): Promise<ChatMessage> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('caption', caption);
    return mapChatMessage(
      await apiRequest<BackendChatMessage>(`/conversations/${conversationId}/messages/image`, {
        method: 'POST',
        formData,
      }),
    );
  },

  async markConversationRead(
    conversationId: string,
    lastReadSeq: number,
  ): Promise<ConversationDetail> {
    return mapConversation(
      await apiRequest<BackendConversation>(`/conversations/${conversationId}/read`, {
        method: 'POST',
        body: { last_read_seq: lastReadSeq },
      }),
    );
  },

  async getMessageAttachmentBlob(conversationId: string, messageId: string): Promise<Blob> {
    return apiRequestBlob(`/conversations/${conversationId}/messages/${messageId}/attachment`);
  },

  async createRealtimeTicket(): Promise<RealtimeTicket> {
    const result = await apiRequest<{ ticket: string; expires_in: number }>('/realtime/ticket', {
      method: 'POST',
    });
    return { ticket: result.ticket, expiresIn: result.expires_in };
  },

  async getPaymentOptions(): Promise<PaymentOptions> {
    const options = await apiRequest<{
      online_channels: PaymentChannel[];
      cash_enabled: boolean;
      currency: string;
    }>('/payments/options');
    return {
      onlineChannels: options.online_channels,
      cashEnabled: options.cash_enabled,
      currency: options.currency,
    };
  },

  /**
   * Ouvre le paiement : seul le moyen choisi est envoyé, le MONTANT est
   * celui du devis accepté, fixé par le serveur (jamais transmis d'ici).
   */
  async initPayment(interventionId: string, channel: PaymentChannel): Promise<PaymentSummary> {
    const payment = await apiRequest<BackendPaymentSummary>('/payments/init', {
      method: 'POST',
      body: { intervention_id: interventionId, channel },
    });
    return mapPaymentSummary(payment);
  },

  async listMyPayments(): Promise<ClientPayment[]> {
    const page = await apiRequest<BackendPage<BackendClientPayment>>('/payments/me');
    return page.items.map((payment) => ({
      id: payment.id,
      interventionId: payment.intervention_id,
      tradeLabel: payment.trade_label,
      artisanName: payment.artisan_name,
      amountFcfa: payment.amount_fcfa,
      channel: payment.channel,
      status: payment.status,
      createdAt: payment.created_at,
      paidAt: payment.paid_at,
      releasedAt: payment.released_at,
      refundedAt: payment.refunded_at,
    }));
  },

  async getMyEarnings(): Promise<ArtisanEarnings> {
    const earnings = await apiRequest<BackendEarnings>('/payments/me/earnings');
    return {
      totals: {
        paidOutFcfa: earnings.totals.paid_out_fcfa,
        payoutPendingFcfa: earnings.totals.payout_pending_fcfa,
        inEscrowFcfa: earnings.totals.in_escrow_fcfa,
        commissionCollectedFcfa: earnings.totals.commission_collected_fcfa,
        cashReceivedFcfa: earnings.totals.cash_received_fcfa,
        commissionDueFcfa: earnings.totals.commission_due_fcfa,
      },
      items: earnings.items.map((item) => ({
        interventionId: item.intervention_id,
        tradeLabel: item.trade_label,
        clientName: item.client_name,
        interventionStatus: item.intervention_status,
        payment: mapPaymentSummary(item.payment),
      })),
    };
  },

  async getPayoutSettings(): Promise<PayoutSettings> {
    return mapPayoutSettings(
      await apiRequest<BackendPayoutSettings>('/payments/me/payout-settings'),
    );
  },

  async updatePayoutSettings(channel: PayoutChannel): Promise<PayoutSettings> {
    return mapPayoutSettings(
      await apiRequest<BackendPayoutSettings>('/payments/me/payout-settings', {
        method: 'PUT',
        body: { channel },
      }),
    );
  },

  async listMyReviews(): Promise<MyReceivedReview[]> {
    // Grande page unique : un artisan relit ses avis récents ; l'historique
    // complet reste servi page par page par l'API si besoin.
    const page = await apiRequest<BackendPage<BackendMyReceivedReview>>(
      `/artisans/me/reviews?page=1&page_size=${MY_REVIEWS_PAGE_SIZE}`,
    );
    return page.items.map(mapMyReceivedReview);
  },

  async reportReview(reviewId: string, reason: string): Promise<MyReceivedReview> {
    return mapMyReceivedReview(
      await apiRequest<BackendMyReceivedReview>(`/artisans/me/reviews/${reviewId}/report`, {
        method: 'POST',
        body: { reason },
      }),
    );
  },

  async listAdminDisputes(filters?: { resolved?: boolean }): Promise<Intervention[]> {
    const query = filters?.resolved ? '?resolved=true' : '';
    const page = await apiRequest<BackendPage<BackendIntervention>>(`/admin/disputes${query}`);
    return page.items.map(mapIntervention);
  },

  async resolveDispute(
    interventionId: string,
    outcome: 'libere' | 'rembourse',
    note: string,
  ): Promise<Intervention> {
    const intervention = await apiRequest<BackendIntervention>(
      `/admin/disputes/${interventionId}/resolve`,
      { method: 'POST', body: { outcome, note } },
    );
    return mapIntervention(intervention);
  },
};
