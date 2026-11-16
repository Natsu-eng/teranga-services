/**
 * Implémentation EN MÉMOIRE d'`ApiClient`, réservée aux TESTS (smoke tests
 * de routage d'App.test.tsx, et mock.test.ts). Jamais importée par le code
 * de production : `index.ts` ne sert que `httpApiClient`, et la règle ESLint
 * `no-restricted-imports` (eslint.config.js) interdit tout import de ce
 * module hors fichiers de test -- il ne peut donc pas réapparaître en
 * silence dans le bundle.
 *
 * Aucune requête réseau ici : l'ancien `analyzeProblem`, qui appelait
 * l'endpoint Express `/api/analyze-problem` (Gemini), est supprimé avec
 * Express (Lot 13) ; il renvoie désormais un résultat fixe et déterministe.
 */
import { INITIAL_ARTISANS, ARTISAN_STATS_BY_ID } from '../../data/mockData';
import type {
  AdminVerificationListItem,
  EngagementCheck,
  RequestEligibility,
  ArtisanEarnings,
  ClientPayment,
  PaymentOptions,
  PaymentSummary,
  PayoutSettings,
  AdminVerificationReview,
  AIAnalysisResult,
  Artisan,
  Intervention,
  MyArtisanProfile,
  MyReceivedReview,
  MyVerification,
  ProfileMediaConstraints,
  Review,
  ServiceRequest,
  Trade,
  VerificationDocument,
} from '../../types';
import {
  ApiError,
  type ApiClient,
  type ArtisanFilters,
  type CreateQuoteInput,
  type CreateReviewInput,
  type CreateServiceRequestInput,
} from './types';
import type { AdminBackofficeApi } from './admin-backoffice';
import type { PageResult } from '../../types/admin';

// Back-office : rien d'inventé. Listes vides, vue d'ensemble à zéro, et
// toute action échoue comme sur un identifiant inconnu.
function emptyPage<T>(): PageResult<T> {
  return { items: [], page: 1, total: 0, totalPages: 0 };
}

const NOT_FOUND = () => new ApiError('not_found', 'Élément introuvable.');

const mockAdminBackoffice: AdminBackofficeApi = {
  async getAdminOverview() {
    await simulateNetworkLatency();
    return {
      artisans: { total: 0, none: 0, pending: 0, verified: 0, rejected: 0, suspended: 0 },
      users: { clients: 0, artisans: 0, admins: 0 },
      interventions: { proposee: 0, acceptee: 0, enCours: 0, terminee: 0, annulee: 0, litige: 0 },
      money: {
        inEscrowFcfa: 0,
        releasedFcfa: 0,
        cashFcfa: 0,
        refundedFcfa: 0,
        businessVolumeFcfa: 0,
        commissionCollectedFcfa: 0,
        commissionDueFcfa: 0,
        commissionPendingFcfa: 0,
      },
      pendingVerifications: 0,
      openDisputes: 0,
      reportedReviews: 0,
      generatedAt: new Date().toISOString(),
    };
  },
  async listAdminArtisans() {
    await simulateNetworkLatency();
    return emptyPage();
  },
  async getAdminArtisan() {
    await simulateNetworkLatency();
    throw NOT_FOUND();
  },
  async suspendArtisan() {
    await simulateNetworkLatency();
    throw NOT_FOUND();
  },
  async reactivateArtisan() {
    await simulateNetworkLatency();
    throw NOT_FOUND();
  },
  async listAdminUsers() {
    await simulateNetworkLatency();
    return emptyPage();
  },
  async grantAdmin() {
    await simulateNetworkLatency();
    throw NOT_FOUND();
  },
  async revokeAdmin() {
    await simulateNetworkLatency();
    throw NOT_FOUND();
  },
  async listAdminReviews() {
    await simulateNetworkLatency();
    return emptyPage();
  },
  async hideReview() {
    await simulateNetworkLatency();
    throw NOT_FOUND();
  },
  async restoreReview() {
    await simulateNetworkLatency();
    throw NOT_FOUND();
  },
  async getCommissionGrid() {
    await simulateNetworkLatency();
    return { items: [], maxRateBps: 0, generatedAt: new Date().toISOString() };
  },
  async addCommissionRate() {
    await simulateNetworkLatency();
    throw NOT_FOUND();
  },
  async listAuditEntries() {
    await simulateNetworkLatency();
    return emptyPage();
  },
};

// Mêmes codes que le seed backend (backend/scripts/seed.py).
const MOCK_TRADES: Trade[] = [
  { id: 'trade-plomberie', code: 'plomberie', labelFr: 'Plomberie' },
  { id: 'trade-electricite', code: 'electricite', labelFr: 'Électricité' },
  { id: 'trade-climatisation', code: 'climatisation', labelFr: 'Climatisation' },
  { id: 'trade-menuiserie', code: 'menuiserie', labelFr: 'Menuiserie' },
  { id: 'trade-maconnerie', code: 'maconnerie', labelFr: 'Maçonnerie' },
  { id: 'trade-peinture', code: 'peinture', labelFr: 'Peinture' },
];

// Latence simulée : les écrans testés traversent ainsi un vrai état de
// chargement, comme avec le backend.
const MIN_LATENCY_MS = 150;
const MAX_LATENCY_MS = 400;

function simulateNetworkLatency(): Promise<void> {
  const delay = MIN_LATENCY_MS + Math.random() * (MAX_LATENCY_MS - MIN_LATENCY_MS);
  return new Promise((resolve) => setTimeout(resolve, delay));
}

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.round(Math.random() * 1000)}`;
}

// Résultat de triage fixe, de même forme que celui de httpApiClient
// (POST /api/v1/ai/analyze) -- jamais présenté à un utilisateur réel.
const FIXTURE_ANALYSIS: AIAnalysisResult = {
  trade: 'Plomberie',
  tradeCode: 'plomberie',
  urgency: 'normale',
  urgencyCode: 'normal',
};

export const mockApiClient: ApiClient = {
  async listArtisans(filters?: ArtisanFilters) {
    await simulateNetworkLatency();
    let results = [...INITIAL_ARTISANS];

    if (filters?.trade) {
      const trade = normalize(filters.trade);
      results = results.filter((artisan) => normalize(artisan.trade) === trade);
    }
    if (filters?.search) {
      const search = normalize(filters.search);
      results = results.filter(
        (artisan) =>
          normalize(artisan.name).includes(search) ||
          normalize(artisan.trade).includes(search) ||
          artisan.tags.some((tag) => normalize(tag).includes(search)),
      );
    }
    if (typeof filters?.minRating === 'number') {
      const minRating = filters.minRating;
      results = results.filter((artisan) => artisan.rating >= minRating);
    }

    return results;
  },

  async getArtisanById(id: string) {
    await simulateNetworkLatency();
    const artisan = INITIAL_ARTISANS.find((item) => item.id === id);
    if (!artisan) {
      throw new ApiError('not_found', "Cet artisan n'existe pas ou n'est plus disponible.");
    }
    return artisan;
  },

  async analyzeProblem(description: string): Promise<AIAnalysisResult> {
    await simulateNetworkLatency();
    if (!description.trim()) {
      throw new ApiError('validation', 'La description est requise.');
    }
    return { ...FIXTURE_ANALYSIS };
  },

  async getArtisanStats(artisanId: string) {
    await simulateNetworkLatency();
    const stats = ARTISAN_STATS_BY_ID[artisanId];
    if (!stats) {
      throw new ApiError('not_found', 'Statistiques indisponibles pour cet artisan.');
    }
    return stats;
  },

  async listTrades() {
    await simulateNetworkLatency();
    return [...MOCK_TRADES];
  },

  // Dead in production (index.ts always routes these to httpApiClient) — kept
  // only so mockApiClient remains a complete ApiClient for mock.test.ts.
  async createServiceRequest(input: CreateServiceRequestInput): Promise<ServiceRequest> {
    await simulateNetworkLatency();
    const trade = MOCK_TRADES.find((item) => item.code === input.tradeCode);
    return {
      id: createId('request'),
      tradeCode: input.tradeCode,
      tradeLabel: trade?.labelFr ?? input.tradeCode,
      description: input.description,
      photoUrl: input.photoUrl ?? null,
      location: input.location,
      locationLabel: input.locationLabel,
      urgency: input.urgency,
      status: 'ouverte',
      expiresAt: null,
      createdAt: new Date().toISOString(),
    };
  },

  async listMyServiceRequests(): Promise<ServiceRequest[]> {
    await simulateNetworkLatency();
    return [];
  },

  async listMyInterventions(): Promise<Intervention[]> {
    await simulateNetworkLatency();
    return [];
  },

  // Messagerie : jamais simulée (le mock est réservé aux tests, qui
  // remplacent ces appels par les leurs).
  async listConversations() {
    await simulateNetworkLatency();
    return [];
  },

  async getUnreadMessageCount() {
    await simulateNetworkLatency();
    return 0;
  },

  async getConversation(): Promise<never> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette conversation n'existe pas.");
  },

  async listMessages() {
    await simulateNetworkLatency();
    return { items: [], hasMore: false };
  },

  async sendMessage(): Promise<never> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette conversation n'existe pas.");
  },

  async sendImageMessage(): Promise<never> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette conversation n'existe pas.");
  },

  async markConversationRead(): Promise<never> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette conversation n'existe pas.");
  },

  async getMessageAttachmentBlob(): Promise<never> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Cette pièce jointe est introuvable.');
  },

  async createRealtimeTicket(): Promise<never> {
    await simulateNetworkLatency();
    throw new ApiError('network', 'Temps réel indisponible.');
  },

  // Notifications push : jamais simulées (désactivées dans le mock).
  async getPushConfig() {
    await simulateNetworkLatency();
    return { enabled: false, vapidPublicKey: null };
  },

  async savePushSubscription(): Promise<never> {
    await simulateNetworkLatency();
    throw new ApiError('validation', 'Les notifications ne sont pas disponibles.');
  },

  async deletePushSubscription() {
    await simulateNetworkLatency();
  },

  async createIntervention(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette demande n'existe pas.");
  },

  async getInterventionById(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async acceptIntervention(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async declineIntervention(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async createQuote(_interventionId: string, _input: CreateQuoteInput): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async acceptQuote(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async refuseQuote(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async completeIntervention(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async createReview(_interventionId: string, _input: CreateReviewInput): Promise<Review> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async updateArtisanAvailability(_isAvailable: boolean): Promise<Artisan> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Profil artisan introuvable.');
  },

  // Mort en production (index.ts route toujours ces méthodes vers
  // httpApiClient, même raisonnement que updateArtisanAvailability
  // ci-dessus) — conservé uniquement pour que mock.ts reste un ApiClient
  // complet pour mock.test.ts.
  async getMyArtisanProfile(): Promise<MyArtisanProfile> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Profil artisan introuvable.');
  },

  async updateMyArtisanProfile(): Promise<MyArtisanProfile> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Profil artisan introuvable.');
  },

  async uploadAvatar(): Promise<MyArtisanProfile> {
    await simulateNetworkLatency();
    throw new ApiError('validation', "L'envoi de la photo a échoué.");
  },

  async uploadCover(): Promise<MyArtisanProfile> {
    await simulateNetworkLatency();
    throw new ApiError('validation', "L'envoi de la photo de couverture a échoué.");
  },

  // Aucune contrainte inventée côté mock : le pré-contrôle se désactive et
  // c'est le serveur qui tranche (voir useProfileMediaConstraints).
  async getProfileMediaConstraints(): Promise<ProfileMediaConstraints> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Contraintes des photos indisponibles.');
  },

  async addArtisanTrade(): Promise<MyArtisanProfile> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Profil artisan introuvable.');
  },

  async removeArtisanTrade(): Promise<MyArtisanProfile> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Profil artisan introuvable.');
  },

  async listMyVerificationDocuments(): Promise<MyVerification> {
    await simulateNetworkLatency();
    return { verifiedStatus: 'none', documents: [] };
  },

  async uploadVerificationDocument(): Promise<VerificationDocument> {
    await simulateNetworkLatency();
    throw new ApiError('validation', "L'envoi du document a échoué.");
  },

  // Mort en production (index.ts route toujours ces méthodes vers
  // httpApiClient, même raisonnement que updateArtisanAvailability
  // ci-dessus) — conservé uniquement pour que mock.ts reste un ApiClient
  // complet pour mock.test.ts.
  async listAdminVerifications(): Promise<AdminVerificationListItem[]> {
    await simulateNetworkLatency();
    return [];
  },

  async getAdminVerificationDocumentBlob(): Promise<Blob> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Document introuvable.');
  },

  async approveVerification(): Promise<AdminVerificationReview> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Document introuvable.');
  },

  async rejectVerification(): Promise<AdminVerificationReview> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Document introuvable.');
  },

  async cancelIntervention(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async openDispute(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async getPaymentOptions(): Promise<PaymentOptions> {
    await simulateNetworkLatency();
    return {
      onlineChannels: ['wave', 'orange_money', 'carte'],
      upcomingChannels: [],
      cashEnabled: true,
      currency: 'XOF',
    };
  },

  async initPayment(): Promise<PaymentSummary> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async listMyPayments(): Promise<ClientPayment[]> {
    await simulateNetworkLatency();
    return [];
  },

  async getMyEarnings(): Promise<ArtisanEarnings> {
    await simulateNetworkLatency();
    return {
      totals: {
        paidOutFcfa: 0,
        payoutPendingFcfa: 0,
        inEscrowFcfa: 0,
        commissionCollectedFcfa: 0,
        cashReceivedFcfa: 0,
        commissionDueFcfa: 0,
      },
      items: [],
    };
  },

  async getPayoutSettings(): Promise<PayoutSettings> {
    await simulateNetworkLatency();
    return {
      channel: 'wave',
      chosen: false,
      allowedChannels: ['wave', 'orange_money'],
      destinationPhone: '+221770000000',
    };
  },

  async updatePayoutSettings(channel): Promise<PayoutSettings> {
    await simulateNetworkLatency();
    return {
      channel,
      chosen: true,
      allowedChannels: ['wave', 'orange_money'],
      destinationPhone: '+221770000000',
    };
  },

  async listMyReviews(): Promise<MyReceivedReview[]> {
    await simulateNetworkLatency();
    return [];
  },

  async reportReview(): Promise<MyReceivedReview> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', 'Avis introuvable.');
  },

  ...mockAdminBackoffice,

  async listAdminDisputes(): Promise<Intervention[]> {
    await simulateNetworkLatency();
    return [];
  },

  async resolveDispute(): Promise<Intervention> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette intervention n'existe pas.");
  },

  async listRequestEligibility(): Promise<RequestEligibility[]> {
    await simulateNetworkLatency();
    return [];
  },

  async checkArtisanCoverage(): Promise<EngagementCheck> {
    await simulateNetworkLatency();
    return { eligible: true, reason: null };
  },

  async cancelServiceRequest(): Promise<ServiceRequest> {
    await simulateNetworkLatency();
    throw new ApiError('not_found', "Cette demande n'existe pas.");
  },
};
