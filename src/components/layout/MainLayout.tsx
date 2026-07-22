import React from 'react';
import { Outlet } from 'react-router';
import { Header } from './Header';
import { BottomNav } from './BottomNav';
import { AppView, UserRole } from '../../types';

interface MainLayoutProps {
  currentView: AppView;
  setCurrentView: (view: AppView) => void;
  userRole: UserRole;
  setUserRole: (role: UserRole) => void;
  location: string;
  setLocation: (loc: string) => void;
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  currentView,
  setCurrentView,
  userRole,
  setUserRole,
  location,
  setLocation,
}) => (
  <div className="min-h-screen bg-background text-foreground font-sans flex flex-col selection:bg-primary selection:text-primary-emerald-foreground">
    <Header
      currentView={currentView}
      setCurrentView={setCurrentView}
      userRole={userRole}
      setUserRole={setUserRole}
      location={location}
      setLocation={setLocation}
    />

    <div className="flex-1">
      <Outlet />
    </div>

    <BottomNav currentView={currentView} setCurrentView={setCurrentView} userRole={userRole} />
  </div>
);
