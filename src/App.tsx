import { useState } from 'react';
import { AppView, UserRole } from './types';
import { Header } from './components/layout/Header';
import { BottomNav } from './components/layout/BottomNav';
import { LandingScreen } from './features/landing/LandingScreen';
import { ClientHomeScreen } from './features/artisans/ClientHomeScreen';
import { DescribeProblemScreen } from './features/ai/DescribeProblemScreen';
import { ArtisanProfileScreen } from './features/artisans/ArtisanProfileScreen';
import { ChatScreen } from './features/chat/ChatScreen';
import { ArtisanDashboardScreen } from './features/requests/ArtisanDashboardScreen';
import { SearchScreen } from './features/artisans/SearchScreen';
import { UserProfileScreen } from './features/profile/UserProfileScreen';

export default function App() {
  const [currentView, setCurrentView] = useState<AppView>('landing');
  const [userRole, setUserRole] = useState<UserRole>('client');
  const [location, setLocation] = useState<string>('Dakar Plateau');
  const [selectedArtisanId, setSelectedArtisanId] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-background text-foreground font-sans flex flex-col selection:bg-primary selection:text-primary-emerald-foreground">
      {/* Top Bar Navigation */}
      <Header
        currentView={currentView}
        setCurrentView={setCurrentView}
        userRole={userRole}
        setUserRole={setUserRole}
        location={location}
        setLocation={setLocation}
      />

      {/* Main Screen Views */}
      <div className="flex-1">
        {currentView === 'landing' && (
          <LandingScreen setCurrentView={setCurrentView} setUserRole={setUserRole} />
        )}

        {currentView === 'client_home' && (
          <ClientHomeScreen
            setCurrentView={setCurrentView}
            setSelectedArtisanId={setSelectedArtisanId}
          />
        )}

        {currentView === 'describe_problem' && (
          <DescribeProblemScreen
            setCurrentView={setCurrentView}
            setSelectedArtisanId={setSelectedArtisanId}
          />
        )}

        {currentView === 'artisan_profile' && selectedArtisanId && (
          <ArtisanProfileScreen artisanId={selectedArtisanId} setCurrentView={setCurrentView} />
        )}

        {currentView === 'chat' && selectedArtisanId && (
          <ChatScreen artisanId={selectedArtisanId} setCurrentView={setCurrentView} />
        )}

        {currentView === 'artisan_dashboard' && (
          <ArtisanDashboardScreen setCurrentView={setCurrentView} />
        )}

        {currentView === 'search' && (
          <SearchScreen setCurrentView={setCurrentView} setSelectedArtisanId={setSelectedArtisanId} />
        )}

        {currentView === 'profile' && (
          <UserProfileScreen
            userRole={userRole}
            setUserRole={setUserRole}
            setCurrentView={setCurrentView}
            location={location}
          />
        )}
      </div>

      {/* Persistent Bottom Navigation */}
      <BottomNav currentView={currentView} setCurrentView={setCurrentView} userRole={userRole} />
    </div>
  );
}
