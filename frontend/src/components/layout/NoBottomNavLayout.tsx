import React from 'react';
import { Outlet } from 'react-router';
import { Header } from './Header';
import { UserRole } from '../../types';

interface NoBottomNavLayoutProps {
  userRole: UserRole;
  setUserRole: (role: UserRole) => void;
  location: string;
  setLocation: (loc: string) => void;
}

export const NoBottomNavLayout: React.FC<NoBottomNavLayoutProps> = ({
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
  </div>
);
