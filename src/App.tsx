import { useState } from 'react';
import { BrowserRouter, Route, Routes, useParams } from 'react-router';
import { UserRole } from './types';
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

function ArtisanProfileRoute() {
  const { artisanId = '' } = useParams<{ artisanId: string }>();
  return <ArtisanProfileScreen artisanId={artisanId} />;
}

function ChatRoute() {
  const { conversationId = '' } = useParams<{ conversationId: string }>();
  return <ChatScreen artisanId={conversationId} />;
}

function AppRoutes() {
  const [userRole, setUserRole] = useState<UserRole>('client');
  const [location, setLocation] = useState<string>('Dakar Plateau');

  return (
    <Routes>
      <Route element={<MinimalLayout />}>
        <Route index element={<LandingScreen setUserRole={setUserRole} />} />
      </Route>

      <Route
        element={
          <NoBottomNavLayout
            userRole={userRole}
            setUserRole={setUserRole}
            location={location}
            setLocation={setLocation}
          />
        }
      >
        <Route path="demande" element={<DescribeProblemScreen />} />
      </Route>

      <Route
        element={
          <MainLayout
            userRole={userRole}
            setUserRole={setUserRole}
            location={location}
            setLocation={setLocation}
          />
        }
      >
        <Route path="accueil" element={<ClientHomeScreen />} />
        <Route path="recherche" element={<SearchScreen />} />
        <Route path="artisans/:artisanId" element={<ArtisanProfileRoute />} />
        <Route path="messages/:conversationId" element={<ChatRoute />} />
        <Route path="pro" element={<ArtisanDashboardScreen />} />
        <Route
          path="profil"
          element={
            <UserProfileScreen userRole={userRole} setUserRole={setUserRole} location={location} />
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
