import { useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import { AuthProvider } from './features/auth/AuthProvider';
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
import { NotFoundScreen } from './features/not-found/NotFoundScreen';
import { AdminVerificationQueueScreen } from './features/admin/AdminVerificationQueueScreen';

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
  const [location, setLocation] = useState<string>('Dakar Plateau');

  return (
    <AuthProvider>
      {/* Canal temps réel unique (messagerie), ouvert seulement si utile. */}
      <RealtimeProvider>
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
            <Route
              path="admin/verifications"
              element={
                <RequireAdminRoute>
                  <AdminVerificationQueueScreen />
                </RequireAdminRoute>
              }
            />
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

          <Route element={<MainLayout location={location} setLocation={setLocation} />}>
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
                  <UserProfileScreen location={location} />
                </ProtectedRoute>
              }
            />
          </Route>

          <Route path="*" element={<NotFoundScreen />} />
        </Routes>
      </RealtimeProvider>
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
