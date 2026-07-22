import React from 'react';
import { Bell, Check, ChevronDown, MapPin, ArrowLeftRight } from 'lucide-react';
import { AppView, UserRole } from '../../types';

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
    <header className="sticky top-0 z-50 flex items-center justify-between h-16 px-4 md:px-8 bg-background/85 backdrop-blur-md border-b border-border">
      {/* Left side */}
      <div className="flex items-center gap-3">
        {userRole === 'artisan' ? (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentView('artisan_dashboard')}
              className="font-headline-md text-lg md:text-xl font-bold text-primary flex items-center gap-2"
            >
              <span className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center text-white text-sm font-bold">
                T
              </span>
              <span>Téranga Pro</span>
            </button>
          </div>
        ) : (
          <div className="flex flex-col relative">
            <button
              onClick={() => setShowLocationPicker(!showLocationPicker)}
              className="flex items-center gap-1 text-muted-foreground text-xs font-sora hover:text-primary transition-colors"
            >
              <MapPin className="text-primary w-[18px] h-[18px]" />
              <span className="font-medium">{location}</span>
              <ChevronDown className="w-4 h-4" />
            </button>
            <h1
              onClick={() => setCurrentView('client_home')}
              className="font-headline-md text-xl md:text-2xl font-bold text-primary cursor-pointer"
            >
              Bonjour
            </h1>

            {showLocationPicker && (
              <div className="absolute top-12 left-0 w-56 bg-white rounded-2xl shadow-xl border border-border p-2 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
                <p className="px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground-soft">
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
                        ? 'bg-primary-emerald/10 text-primary font-semibold'
                        : 'text-foreground hover:bg-surface-muted'
                    }`}
                  >
                    <span>{loc}</span>
                    {location === loc && <Check className="w-4 h-4" />}
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
          className="px-3 py-1.5 rounded-full bg-accent-soft/50 text-accent-foreground text-xs font-sora font-semibold flex items-center gap-1.5 border border-accent-soft hover:bg-accent-soft transition-all"
          title="Basculer entre l'espace Client et l'espace Artisan Pro"
        >
          <ArrowLeftRight className="w-4 h-4" />
          <span className="hidden sm:inline">
            {userRole === 'client' ? 'Mode Artisan Pro' : 'Espace Client'}
          </span>
          <span className="sm:hidden">{userRole === 'client' ? 'Pro' : 'Client'}</span>
        </button>

        {/* Notifications */}
        <button
          onClick={() => setCurrentView(userRole === 'artisan' ? 'artisan_dashboard' : 'chat')}
          className="relative w-10 h-10 flex items-center justify-center rounded-full bg-surface-muted hover:bg-border-subtle text-muted-foreground transition-colors"
        >
          <Bell className="w-6 h-6" />
          {unreadCount > 0 && (
            <span className="absolute top-2 right-2 w-2 h-2 bg-destructive rounded-full animate-ping" />
          )}
        </button>
      </div>
    </header>
  );
};
