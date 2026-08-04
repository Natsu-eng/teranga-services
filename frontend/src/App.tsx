import { useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import { AuthProvider } from './features/auth/AuthProvider';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { MainLayout } from './components/layout/MainLayout';
import { NoBottomNavLayout } from './components/layout/NoBottomNavLayout';
import { MinimalLayout } from './components/layout/MinimalLayout';
import { LandingScreen } from './features/landing/LandingScreen';
import { AuthEntryScreen } from './features/auth/AuthEntryScreen';
import { RoleSelectScreen } from './features/auth/RoleSelectScreen';
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
import { NotFoundScreen } from './features/not-found/NotFoundScreen';
import { ComingSoon } from './components/ui/ComingSoon';

export function AppRoutes() {
  const [location, setLocation] = useState<string>('Dakar Plateau');

  return (
    <AuthProvider>
      <Routes>
        <Route element={<MinimalLayout />}>
          <Route index element={<LandingScreen />} />
          <Route path="connexion" element={<AuthEntryScreen />} />
          <Route path="connexion/role" element={<RoleSelectScreen />} />
          <Route path="connexion/telephone" element={<PhoneScreen />} />
          <Route path="connexion/code" element={<OtpScreen />} />
        </Route>

        <Route element={<NoBottomNavLayout location={location} setLocation={setLocation} />}>
          <Route path="demande" element={<DescribeProblemScreen />} />
        </Route>

        <Route element={<MainLayout location={location} setLocation={setLocation} />}>
          <Route path="accueil" element={<ClientHomeScreen />} />
          <Route path="recherche" element={<SearchScreen />} />
          <Route path="artisans/:artisanId" element={<ArtisanProfileScreen />} />
          <Route
            path="messages/:conversationId"
            element={
              <ProtectedRoute>
                <ComingSoon
                  title="La messagerie arrive bientôt"
                  description="Les échanges avec les artisans depuis l'application seront bientôt disponibles."
                />
              </ProtectedRoute>
            }
          />
          <Route
            path="pro"
            element={
              <ProtectedRoute>
                <ArtisanDashboardScreen />
              </ProtectedRoute>
            }
          />
          <Route
            path="pro/onboarding"
            element={
              <ProtectedRoute>
                <ArtisanOnboardingScreen />
              </ProtectedRoute>
            }
          />
          <Route
            path="bienvenue-artisan"
            element={
              <ProtectedRoute>
                <ArtisanWelcomeScreen />
              </ProtectedRoute>
            }
          />
          <Route
            path="mes-demandes"
            element={
              <ProtectedRoute>
                <MyRequestsScreen />
              </ProtectedRoute>
            }
          />
          <Route
            path="mes-interventions"
            element={
              <ProtectedRoute>
                <InterventionsScreen />
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
