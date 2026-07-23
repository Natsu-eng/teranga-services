import React from 'react';
import { Outlet } from 'react-router';

export const MinimalLayout: React.FC = () => (
  <div className="min-h-screen bg-background text-foreground font-sans flex flex-col selection:bg-primary selection:text-primary-emerald-foreground">
    <div className="flex-1">
      <Outlet />
    </div>
  </div>
);
