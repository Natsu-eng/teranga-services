import React from 'react';
import { AppView, UserRole } from '../types';

interface BottomNavProps {
  currentView: AppView;
  setCurrentView: (view: AppView) => void;
  userRole: UserRole;
}

export const BottomNav: React.FC<BottomNavProps> = ({
  currentView,
  setCurrentView,
  userRole,
}) => {
  if (currentView === 'landing' || currentView === 'describe_problem') return null;

  if (userRole === 'artisan') {
    return (
      <nav className="fixed bottom-0 left-0 right-0 z-40 flex justify-around items-center px-4 py-2 bg-[#fcf9f8] border-t border-[#e5e2e1] shadow-lg pb-safe">
        <button
          onClick={() => setCurrentView('artisan_dashboard')}
          className={`flex flex-col items-center justify-center px-5 py-1.5 rounded-full transition-all ${
            currentView === 'artisan_dashboard'
              ? 'bg-[#0e5a3c] text-white shadow-sm'
              : 'text-[#404943] hover:bg-[#f6f3f2]'
          }`}
        >
          <span className="material-symbols-outlined text-[20px]">assignment</span>
          <span className="font-sora text-[11px] font-medium mt-0.5">Demandes</span>
        </button>

        <button
          onClick={() => setCurrentView('artisan_dashboard')}
          className="flex flex-col items-center justify-center px-4 py-1.5 rounded-full text-[#404943] hover:bg-[#f6f3f2] transition-all"
        >
          <span className="material-symbols-outlined text-[20px]">payments</span>
          <span className="font-sora text-[11px] font-medium mt-0.5">Revenus</span>
        </button>

        <button
          onClick={() => setCurrentView('chat')}
          className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
            currentView === 'chat'
              ? 'bg-[#0e5a3c] text-white'
              : 'text-[#404943] hover:bg-[#f6f3f2]'
          }`}
        >
          <span className="material-symbols-outlined text-[20px]">chat_bubble</span>
          <span className="font-sora text-[11px] font-medium mt-0.5">Messages</span>
        </button>

        <button
          onClick={() => setCurrentView('profile')}
          className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
            currentView === 'profile'
              ? 'bg-[#0e5a3c] text-white'
              : 'text-[#404943] hover:bg-[#f6f3f2]'
          }`}
        >
          <span className="material-symbols-outlined text-[20px]">person</span>
          <span className="font-sora text-[11px] font-medium mt-0.5">Profil</span>
        </button>
      </nav>
    );
  }

  // Client role navigation
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 flex justify-around items-center px-4 py-2 bg-[#fcf9f8] border-t border-[#e5e2e1] shadow-lg pb-safe">
      <button
        onClick={() => setCurrentView('client_home')}
        className={`flex flex-col items-center justify-center px-5 py-1.5 rounded-full transition-all ${
          currentView === 'client_home'
            ? 'bg-[#0e5a3c] text-[#8acfa9] font-semibold'
            : 'text-[#404943] hover:bg-[#f6f3f2]'
        }`}
      >
        <span className={`material-symbols-outlined text-[20px] ${currentView === 'client_home' ? 'fill-icon' : ''}`}>
          home
        </span>
        <span className="font-sora text-[11px] mt-0.5">Accueil</span>
      </button>

      <button
        onClick={() => setCurrentView('search')}
        className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
          currentView === 'search'
            ? 'bg-[#0e5a3c] text-[#8acfa9] font-semibold'
            : 'text-[#404943] hover:bg-[#f6f3f2]'
        }`}
      >
        <span className="material-symbols-outlined text-[20px]">search</span>
        <span className="font-sora text-[11px] mt-0.5">Recherche</span>
      </button>

      <button
        onClick={() => setCurrentView('chat')}
        className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
          currentView === 'chat'
            ? 'bg-[#0e5a3c] text-[#8acfa9] font-semibold'
            : 'text-[#404943] hover:bg-[#f6f3f2]'
        }`}
      >
        <span className="material-symbols-outlined text-[20px]">chat_bubble</span>
        <span className="font-sora text-[11px] mt-0.5">Messages</span>
      </button>

      <button
        onClick={() => setCurrentView('profile')}
        className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
          currentView === 'profile'
            ? 'bg-[#0e5a3c] text-[#8acfa9] font-semibold'
            : 'text-[#404943] hover:bg-[#f6f3f2]'
        }`}
      >
        <span className="material-symbols-outlined text-[20px]">person</span>
        <span className="font-sora text-[11px] mt-0.5">Profil</span>
      </button>
    </nav>
  );
};
