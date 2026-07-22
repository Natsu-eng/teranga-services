import { useEffect, useState } from 'react';
import { BrowserRouter, Route, Routes, useLocation, useParams } from 'react-router';
import { AppView, UserRole } from './types';
import { MainLayout } from './components/layout/MainLayout';
import { NoBottomNavLayout } from './components/layout/NoBottomNavLayout';
import { MinimalLayout } from './components/layout/MinimalLayout';
import { LandingScreen } from './features/landing/LandingScreen';
import { ClientHomeScreen } from './features/artisans/ClientHomeScreen';
import { DescribeProblemScreen } from './features/ai/DescribeProblemScreen';
import { ArtisanProfileScreen } from './features/artisans/ArtisanProfileScreen';
import { ChatScreen } from './features/chat/ChatScreen';
import { ArtisanDashboardScreen } from './features/requests/ArtisanDashboardScreen';
import { SearchScreen } from './features/artisans/SearchScreen';
import { UserProfileScreen } from './features/profile/UserProfileScreen';
import { NotFoundScreen } from './features/not-found/NotFoundScreen';
import { pathToView, useLegacyArtisanNavigation } from './routes/legacyNavigation';

interface ArtisanProfileRouteProps {
  setCurrentView: (view: AppView) => void;
  setSelectedArtisanId: (id: string) => void;
}

function ArtisanProfileRoute({ setCurrentView, setSelectedArtisanId }: ArtisanProfileRouteProps) {
  const { artisanId = '' } = useParams<{ artisanId: string }>();

  useEffect(() => {
    setSelectedArtisanId(artisanId);
  }, [artisanId, setSelectedArtisanId]);

  return <ArtisanProfileScreen artisanId={artisanId} setCurrentView={setCurrentView} />;
}

function ChatRoute({ setCurrentView, setSelectedArtisanId }: ArtisanProfileRouteProps) {
  const { conversationId = '' } = useParams<{ conversationId: string }>();

  useEffect(() => {
    setSelectedArtisanId(conversationId);
  }, [conversationId, setSelectedArtisanId]);

  return <ChatScreen artisanId={conversationId} setCurrentView={setCurrentView} />;
}

function AppRoutes() {
  const [userRole, setUserRole] = useState<UserRole>('client');
  const [location, setLocation] = useState<string>('Dakar Plateau');
  const { setSelectedArtisanId, setCurrentView } = useLegacyArtisanNavigation();
  const currentView = pathToView(useLocation().pathname);

  return (
    <Routes>
      <Route element={<MinimalLayout />}>
        <Route index element={<LandingScreen setCurrentView={setCurrentView} setUserRole={setUserRole} />} />
      </Route>

      <Route
        element={
          <NoBottomNavLayout
            currentView={currentView}
            setCurrentView={setCurrentView}
            userRole={userRole}
            setUserRole={setUserRole}
            location={location}
            setLocation={setLocation}
          />
        }
      >
        <Route
          path="demande"
          element={
            <DescribeProblemScreen
              setCurrentView={setCurrentView}
              setSelectedArtisanId={setSelectedArtisanId}
            />
          }
        />
      </Route>

      <Route
        element={
          <MainLayout
            currentView={currentView}
            setCurrentView={setCurrentView}
            userRole={userRole}
            setUserRole={setUserRole}
            location={location}
            setLocation={setLocation}
          />
        }
      >
        <Route
          path="accueil"
          element={
            <ClientHomeScreen setCurrentView={setCurrentView} setSelectedArtisanId={setSelectedArtisanId} />
          }
        />
        <Route
          path="recherche"
          element={<SearchScreen setCurrentView={setCurrentView} setSelectedArtisanId={setSelectedArtisanId} />}
        />
        <Route
          path="artisans/:artisanId"
          element={
            <ArtisanProfileRoute setCurrentView={setCurrentView} setSelectedArtisanId={setSelectedArtisanId} />
          }
        />
        <Route
          path="messages/:conversationId"
          element={<ChatRoute setCurrentView={setCurrentView} setSelectedArtisanId={setSelectedArtisanId} />}
        />
        <Route path="pro" element={<ArtisanDashboardScreen setCurrentView={setCurrentView} />} />
        <Route
          path="profil"
          element={
            <UserProfileScreen
              userRole={userRole}
              setUserRole={setUserRole}
              setCurrentView={setCurrentView}
              location={location}
            />
          }
        />
      </Route>

      <Route path="*" element={<NotFoundScreen />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
