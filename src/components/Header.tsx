import React from 'react';
import { AppView, UserRole } from '../types';

interface HeaderProps {
  currentView: AppView;
  setCurrentView: (view: AppView) => void;
  userRole: UserRole;
  setUserRole: (role: UserRole) => void;
  location: string;
  setLocation: (loc: string) => void;
  unreadCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  currentView,
  setCurrentView,
  userRole,
  setUserRole,
  location,
  setLocation,
  unreadCount = 2,
}) => {
  const [showLocationPicker, setShowLocationPicker] = React.useState(false);

  const locations = [
    'Dakar Plateau',
    'Almadies, Dakar',
    'Ouakam, Dakar',
    'Mermoz - Sacré Cœur',
    'Yoff - Ngor',
    'Point E, Dakar',
  ];

  if (currentView === 'landing') return null;

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between h-16 px-4 md:px-8 bg-[#fcf9f8]/85 backdrop-blur-md border-b border-[#e5e2e1]">
      {/* Left side */}
      <div className="flex items-center gap-3">
        {userRole === 'artisan' ? (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentView('artisan_dashboard')}
              className="font-headline-md text-lg md:text-xl font-bold text-[#004129] flex items-center gap-2"
            >
              <span className="w-8 h-8 bg-[#004129] rounded-lg flex items-center justify-center text-white text-sm font-bold">
                T
              </span>
              <span>Téranga Pro</span>
            </button>
          </div>
        ) : (
          <div className="flex flex-col relative">
            <button
              onClick={() => setShowLocationPicker(!showLocationPicker)}
              className="flex items-center gap-1 text-[#404943] text-xs font-sora hover:text-[#004129] transition-colors"
            >
              <span className="material-symbols-outlined text-[#004129] text-[18px]">
                location_on
              </span>
              <span className="font-medium">{location}</span>
              <span className="material-symbols-outlined text-[16px]">expand_more</span>
            </button>
            <h1
              onClick={() => setCurrentView('client_home')}
              className="font-headline-md text-xl md:text-2xl font-bold text-[#004129] cursor-pointer"
            >
              Bonjour
            </h1>

            {showLocationPicker && (
              <div className="absolute top-12 left-0 w-56 bg-white rounded-2xl shadow-xl border border-[#e5e2e1] p-2 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
                <p className="px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-[#707972]">
                  Quartier à Dakar
                </p>
                {locations.map((loc) => (
                  <button
                    key={loc}
                    onClick={() => {
                      setLocation(loc);
                      setShowLocationPicker(false);
                    }}
                    className={`w-full text-left px-3 py-2 text-sm rounded-xl transition-colors flex items-center justify-between ${
                      location === loc
                        ? 'bg-[#0e5a3c]/10 text-[#004129] font-semibold'
                        : 'text-[#1c1b1b] hover:bg-[#f6f3f2]'
                    }`}
                  >
                    <span>{loc}</span>
                    {location === loc && (
                      <span className="material-symbols-outlined text-sm">check</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right side controls */}
      <div className="flex items-center gap-2">
        {/* Role Switcher Pill */}
        <button
          onClick={() => {
            const nextRole = userRole === 'client' ? 'artisan' : 'client';
            setUserRole(nextRole);
            setCurrentView(nextRole === 'artisan' ? 'artisan_dashboard' : 'client_home');
          }}
          className="px-3 py-1.5 rounded-full bg-[#ffddb1]/50 text-[#815600] text-xs font-sora font-semibold flex items-center gap-1.5 border border-[#ffddb1] hover:bg-[#ffddb1] transition-all"
          title="Basculer entre l'espace Client et l'espace Artisan Pro"
        >
          <span className="material-symbols-outlined text-[16px]">swap_horiz</span>
          <span className="hidden sm:inline">
            {userRole === 'client' ? 'Mode Artisan Pro' : 'Espace Client'}
          </span>
          <span className="sm:hidden">{userRole === 'client' ? 'Pro' : 'Client'}</span>
        </button>

        {/* Notifications */}
        <button
          onClick={() => setCurrentView(userRole === 'artisan' ? 'artisan_dashboard' : 'chat')}
          className="relative w-10 h-10 flex items-center justify-center rounded-full bg-[#f6f3f2] hover:bg-[#eae7e7] text-[#404943] transition-colors"
        >
          <span className="material-symbols-outlined">notifications</span>
          {unreadCount > 0 && (
            <span className="absolute top-2 right-2 w-2 h-2 bg-[#ba1a1a] rounded-full animate-ping" />
          )}
        </button>
      </div>
    </header>
  );
};
