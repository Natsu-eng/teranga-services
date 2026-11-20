import { BrowserRouter, Route, Routes } from 'react-router';
import { AuthProvider } from './features/auth/AuthProvider';
import { PlaceProvider } from './features/location/PlaceProvider';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { RequireAdminRoute } from './components/auth/RequireAdminRoute';
import { MainLayout } from './components/layout/MainLayout';
import { MinimalLayout } from './components/layout/MinimalLayout';
import { SubPageLayout } from './components/layout/SubPageLayout';
import { LandingScreen } from './features/landing/LandingScreen';
import { AuthEntryScreen } from './features/auth/AuthEntryScreen';
import { RoleSelectScreen } from './features/auth/RoleSelectScreen';
import { NameScreen } from './features/auth/NameScreen';
import { PhoneScreen } from './features/auth/PhoneScreen';
import { OtpScreen } from './features/auth/OtpScreen';
import { ArtisanWelcomeScreen } from './features/auth/ArtisanWelcomeScreen';
import { ClientHomeScreen } from './features/artisans/ClientHomeScreen';
import { DescribeProblemScreen } from './features/ai/DescribeProblemScreen';
import { ArtisanProfileScreen } from './features/artisans/ArtisanProfileScreen';
import { ArtisanDashboardScreen } from './features/artisans/ArtisanDashboardScreen';
import { ArtisanOnboardingScreen } from './features/artisans/ArtisanOnboardingScreen';
import { SearchScreen } from './features/artisans/SearchScreen';
import { MyRequestsScreen } from './features/requests/MyRequestsScreen';
import { InterventionsScreen } from './features/interventions/InterventionsScreen';
import { UserProfileScreen } from './features/profile/UserProfileScreen';
import { MessagesScreen } from './features/messages/MessagesScreen';
import { ConversationScreen } from './features/messages/ConversationScreen';
import { RealtimeProvider } from './features/messages/realtime/RealtimeProvider';
import { PushSubscriptionSync } from './features/notifications/PushSubscriptionSync';
import { NotFoundScreen } from './features/not-found/NotFoundScreen';
import { AdminVerificationQueueScreen } from './features/admin/AdminVerificationQueueScreen';
import { AdminDisputesScreen } from './features/admin/AdminDisputesScreen';
import { AdminLayout } from './features/admin/AdminLayout';
import { AdminOverviewScreen } from './features/admin/AdminOverviewScreen';
import { AdminArtisansScreen } from './features/admin/AdminArtisansScreen';
import { AdminArtisanDetailScreen } from './features/admin/AdminArtisanDetailScreen';
import { AdminUsersScreen } from './features/admin/AdminUsersScreen';
import { AdminReviewsScreen } from './features/admin/AdminReviewsScreen';
import { AdminCommissionsScreen } from './features/admin/AdminCommissionsScreen';
import { AdminAuditScreen } from './features/admin/AdminAuditScreen';
import { AdminSupportScreen } from './features/admin/AdminSupportScreen';
import { SupportScreen } from './features/support/SupportScreen';
import { PaymentScreen } from './features/payments/PaymentScreen';
import { MyPaymentsScreen } from './features/payments/MyPaymentsScreen';
import { EarningsScreen } from './features/payments/EarningsScreen';

/*
 * Rôles autorisés par espace, alignés sur les gardes du backend
 * (require_role) : /requests/me est réservé aux clients, /interventions/me
 * aux clients et artisans, tout /pro aux artisans. Les routes sans `roles`
 * (profil, messagerie) acceptent tout compte connecté. L'espace admin a sa
 * propre garde (RequireAdminRoute, indétectable pour un non-admin).
 */
const ARTISAN_ONLY = ['artisan'] as const;
const CLIENT_ONLY = ['client'] as const;
const CLIENT_OR_ARTISAN = ['client', 'artisan'] as const;

/*
 * Trois gabarits :
 * - MinimalLayout : pages autonomes (marketing, connexion, bienvenue, admin) ;
 * - SubPageLayout : sous-pages avec leur propre AppBar (titre + retour) ;
 * - MainLayout    : écrans « onglets » avec en-tête et navigation basse,
 *                   habillés client (clair) ou Pro (vert profond) selon le rôle.
 */
export function AppRoutes() {
  return (
    <AuthProvider>
      {/* Lieu d'intervention partagé : quartier de l'en-tête = lieu proposé aux demandes. */}
      <PlaceProvider>
        {/* Canal temps réel unique (messagerie), ouvert seulement si utile. */}
        <RealtimeProvider>
          {/* Notifications push : abonnement de l'appareil tenu à jour (sans rien afficher). */}
          <PushSubscriptionSync />
          <Routes>
            <Route element={<MinimalLayout />}>
              <Route index element={<LandingScreen />} />
              <Route path="connexion" element={<AuthEntryScreen />} />
              <Route path="connexion/role" element={<RoleSelectScreen />} />
              <Route path="connexion/nom" element={<NameScreen />} />
              <Route path="connexion/telephone" element={<PhoneScreen />} />
              <Route path="connexion/code" element={<OtpScreen />} />
              <Route
                path="bienvenue-artisan"
                element={
                  <ProtectedRoute roles={ARTISAN_ONLY}>
                    <ArtisanWelcomeScreen />
                  </ProtectedRoute>
                }
              />
              {/* Back-office : une seule garde pour toute la coquille et ses sections. */}
              <Route
                path="admin"
                element={
                  <RequireAdminRoute>
                    <AdminLayout />
                  </RequireAdminRoute>
                }
              >
                <Route index element={<AdminOverviewScreen />} />
                <Route path="verifications" element={<AdminVerificationQueueScreen />} />
                <Route path="artisans" element={<AdminArtisansScreen />} />
                <Route path="artisans/:artisanId" element={<AdminArtisanDetailScreen />} />
                <Route path="utilisateurs" element={<AdminUsersScreen />} />
                <Route path="avis" element={<AdminReviewsScreen />} />
                <Route path="litiges" element={<AdminDisputesScreen />} />
                <Route path="commissions" element={<AdminCommissionsScreen />} />
                <Route path="journal" element={<AdminAuditScreen />} />
                <Route path="support" element={<AdminSupportScreen />} />
                <Route path="*" element={<NotFoundScreen />} />
              </Route>
            </Route>

            <Route element={<SubPageLayout />}>
              <Route path="demande" element={<DescribeProblemScreen />} />
              <Route path="artisans/:artisanId" element={<ArtisanProfileScreen />} />
              <Route
                path="mes-demandes"
                element={
                  <ProtectedRoute roles={CLIENT_ONLY}>
                    <MyRequestsScreen />
                  </ProtectedRoute>
                }
              />
              <Route
                path="mes-interventions"
                element={
                  <ProtectedRoute roles={CLIENT_OR_ARTISAN}>
                    <InterventionsScreen />
                  </ProtectedRoute>
                }
              />
              {/* Paiement d'une intervention (client) ; page de retour du fournisseur. */}
              <Route
                path="paiement/:interventionId"
                element={
                  <ProtectedRoute roles={CLIENT_ONLY}>
                    <PaymentScreen />
                  </ProtectedRoute>
                }
              />
              {/* Aide : écrire à Téranga et suivre ses demandes (client et artisan). */}
              <Route
                path="aide"
                element={
                  <ProtectedRoute roles={CLIENT_OR_ARTISAN}>
                    <SupportScreen />
                  </ProtectedRoute>
                }
              />
              <Route
                path="mes-paiements"
                element={
                  <ProtectedRoute roles={CLIENT_ONLY}>
                    <MyPaymentsScreen />
                  </ProtectedRoute>
                }
              />
              <Route
                path="pro/gains"
                element={
                  <ProtectedRoute roles={ARTISAN_ONLY}>
                    <EarningsScreen />
                  </ProtectedRoute>
                }
              />
              <Route
                path="pro/onboarding"
                element={
                  <ProtectedRoute roles={ARTISAN_ONLY}>
                    <ArtisanOnboardingScreen />
                  </ProtectedRoute>
                }
              />
              {/* Fil de discussion : plein écran, saisie collée en bas. Réservé aux
              deux participants (vérifié par le serveur, 403 sinon). */}
              <Route
                path="messages/:conversationId"
                element={
                  <ProtectedRoute roles={CLIENT_OR_ARTISAN}>
                    <ConversationScreen />
                  </ProtectedRoute>
                }
              />
            </Route>

            <Route element={<MainLayout />}>
              <Route path="accueil" element={<ClientHomeScreen />} />
              <Route path="recherche" element={<SearchScreen />} />
              {/* Liste des discussions (entrée « Messages » de la navigation). */}
              <Route
                path="messages"
                element={
                  <ProtectedRoute roles={CLIENT_OR_ARTISAN}>
                    <MessagesScreen />
                  </ProtectedRoute>
                }
              />
              <Route
                path="pro"
                element={
                  <ProtectedRoute roles={ARTISAN_ONLY}>
                    <ArtisanDashboardScreen />
                  </ProtectedRoute>
                }
              />
              <Route
                path="profil"
                element={
                  <ProtectedRoute>
                    <UserProfileScreen />
                  </ProtectedRoute>
                }
              />
            </Route>

            <Route path="*" element={<NotFoundScreen />} />
          </Routes>
        </RealtimeProvider>
      </PlaceProvider>
    </AuthProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
