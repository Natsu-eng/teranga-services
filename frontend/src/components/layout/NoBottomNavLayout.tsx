import React from 'react';
import { Outlet } from 'react-router';
import { Header } from './Header';

interface NoBottomNavLayoutProps {
  location: string;
  setLocation: (loc: string) => void;
}

export const NoBottomNavLayout: React.FC<NoBottomNavLayoutProps> = ({ location, setLocation }) => (
  <div className="min-h-screen bg-background text-foreground font-sans flex flex-col selection:bg-primary selection:text-primary-emerald-foreground">
    <Header location={location} setLocation={setLocation} />

    <div className="flex-1">
      <Outlet />
    </div>
  </div>
);
