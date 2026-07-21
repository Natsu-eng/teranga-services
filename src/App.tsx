import { useState } from 'react';
import { AppView, UserRole, Artisan } from './types';
import { INITIAL_ARTISANS, INITIAL_JOB_REQUESTS, INITIAL_CHAT_MESSAGES } from './data/mockData';
import { Header } from './components/Header';
import { BottomNav } from './components/BottomNav';
import { LandingScreen } from './components/LandingScreen';
import { ClientHomeScreen } from './components/ClientHomeScreen';
import { DescribeProblemScreen } from './components/DescribeProblemScreen';
import { ArtisanProfileScreen } from './components/ArtisanProfileScreen';
import { ChatScreen } from './components/ChatScreen';
import { ArtisanDashboardScreen } from './components/ArtisanDashboardScreen';
import { SearchScreen } from './components/SearchScreen';
import { UserProfileScreen } from './components/UserProfileScreen';

export default function App() {
  const [currentView, setCurrentView] = useState<AppView>('landing');
  const [userRole, setUserRole] = useState<UserRole>('client');
  const [artisans] = useState<Artisan[]>(INITIAL_ARTISANS);
  const [selectedArtisan, setSelectedArtisan] = useState<Artisan>(INITIAL_ARTISANS[0]);
  const [jobRequests, setJobRequests] = useState(INITIAL_JOB_REQUESTS);
  const [chatMessages, setChatMessages] = useState(INITIAL_CHAT_MESSAGES);
  const [location, setLocation] = useState<string>('Dakar Plateau');
  const [searchQuery, setSearchQuery] = useState<string>('');

  return (
    <div className="min-h-screen bg-[#fcf9f8] text-[#1c1b1b] font-sans flex flex-col selection:bg-[#004129] selection:text-[#8acfa9]">
      {/* Top Bar Navigation */}
      <Header
        currentView={currentView}
        setCurrentView={setCurrentView}
        userRole={userRole}
        setUserRole={setUserRole}
        location={location}
        setLocation={setLocation}
        unreadCount={chatMessages.length > 0 ? 1 : 0}
      />

      {/* Main Screen Views */}
      <div className="flex-1">
        {currentView === 'landing' && (
          <LandingScreen setCurrentView={setCurrentView} setUserRole={setUserRole} />
        )}

        {currentView === 'client_home' && (
          <ClientHomeScreen
            artisans={artisans}
            setCurrentView={setCurrentView}
            setSelectedArtisan={setSelectedArtisan}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
          />
        )}

        {currentView === 'describe_problem' && (
          <DescribeProblemScreen
            setCurrentView={setCurrentView}
            setSelectedArtisan={setSelectedArtisan}
            artisans={artisans}
          />
        )}

        {currentView === 'artisan_profile' && (
          <ArtisanProfileScreen
            artisan={selectedArtisan}
            setCurrentView={setCurrentView}
          />
        )}

        {currentView === 'chat' && (
          <ChatScreen
            artisan={selectedArtisan}
            messages={chatMessages}
            setMessages={setChatMessages}
            setCurrentView={setCurrentView}
          />
        )}

        {currentView === 'artisan_dashboard' && (
          <ArtisanDashboardScreen
            artisan={artisans[0]}
            jobRequests={jobRequests}
            setJobRequests={setJobRequests}
            setCurrentView={setCurrentView}
          />
        )}

        {currentView === 'search' && (
          <SearchScreen
            artisans={artisans}
            setCurrentView={setCurrentView}
            setSelectedArtisan={setSelectedArtisan}
          />
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
      <BottomNav
        currentView={currentView}
        setCurrentView={setCurrentView}
        userRole={userRole}
      />
    </div>
  );
}
