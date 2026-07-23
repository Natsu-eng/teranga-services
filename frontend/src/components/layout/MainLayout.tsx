import React from 'react';
import { Outlet } from 'react-router';
import { Header } from './Header';
import { BottomNav } from './BottomNav';
import { UserRole } from '../../types';

interface MainLayoutProps {
  userRole: UserRole;
  setUserRole: (role: UserRole) => void;
  location: string;
  setLocation: (loc: string) => void;
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  userRole,
  setUserRole,
  location,
  setLocation,
}) => (
  <div className="min-h-screen bg-background text-foreground font-sans flex flex-col selection:bg-primary selection:text-primary-emerald-foreground">
    <Header userRole={userRole} setUserRole={setUserRole} location={location} setLocation={setLocation} />

    <div className="flex-1">
      <Outlet />
    </div>

    <BottomNav userRole={userRole} />
  </div>
);
