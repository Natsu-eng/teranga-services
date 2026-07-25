import React from 'react';
import { ClipboardList, Wallet, MessageCircle, User, Home, Search } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useAuth } from '../../features/auth/hooks/useAuth';
import { toDisplayRole } from '../../features/auth/role';
import { useCurrentUser } from '../../features/profile/hooks/useCurrentUser';

export const BottomNav: React.FC = () => {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const auth = useAuth();
  const userRole = toDisplayRole(auth.role);
  const { data: currentUser } = useCurrentUser();

  const goToMessages = () => {
    if (currentUser) navigate(`/messages/${currentUser.artisanId}`);
  };

  const isMessagesActive = pathname.startsWith('/messages');

  if (userRole === 'artisan') {
    return (
      <nav className="fixed bottom-0 left-0 right-0 z-40 flex justify-around items-center px-4 py-2 bg-background border-t border-border shadow-lg pb-safe">
        <Link
          to="/pro"
          className={`flex flex-col items-center justify-center px-5 py-1.5 rounded-full transition-all ${
            pathname === '/pro'
              ? 'bg-primary-emerald text-white shadow-sm'
              : 'text-muted-foreground hover:bg-surface-muted'
          }`}
        >
          <ClipboardList className="w-5 h-5" />
          <span className="font-sora text-[11px] font-medium mt-0.5">Demandes</span>
        </Link>

        <Link
          to="/pro"
          className="flex flex-col items-center justify-center px-4 py-1.5 rounded-full text-muted-foreground hover:bg-surface-muted transition-all"
        >
          <Wallet className="w-5 h-5" />
          <span className="font-sora text-[11px] font-medium mt-0.5">Revenus</span>
        </Link>

        <button
          onClick={goToMessages}
          className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
            isMessagesActive ? 'bg-primary-emerald text-white' : 'text-muted-foreground hover:bg-surface-muted'
          }`}
        >
          <MessageCircle className="w-5 h-5" />
          <span className="font-sora text-[11px] font-medium mt-0.5">Messages</span>
        </button>

        <Link
          to="/profil"
          className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
            pathname === '/profil'
              ? 'bg-primary-emerald text-white'
              : 'text-muted-foreground hover:bg-surface-muted'
          }`}
        >
          <User className="w-5 h-5" />
          <span className="font-sora text-[11px] font-medium mt-0.5">Profil</span>
        </Link>
      </nav>
    );
  }

  // Client role navigation
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 flex justify-around items-center px-4 py-2 bg-background border-t border-border shadow-lg pb-safe">
      <Link
        to="/accueil"
        className={`flex flex-col items-center justify-center px-5 py-1.5 rounded-full transition-all ${
          pathname === '/accueil'
            ? 'bg-primary-emerald text-primary-emerald-foreground font-semibold'
            : 'text-muted-foreground hover:bg-surface-muted'
        }`}
      >
        <Home className="w-5 h-5" {...(pathname === '/accueil' ? { fill: 'currentColor' } : {})} />
        <span className="font-sora text-[11px] mt-0.5">Accueil</span>
      </Link>

      <Link
        to="/recherche"
        className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
          pathname === '/recherche'
            ? 'bg-primary-emerald text-primary-emerald-foreground font-semibold'
            : 'text-muted-foreground hover:bg-surface-muted'
        }`}
      >
        <Search className="w-5 h-5" />
        <span className="font-sora text-[11px] mt-0.5">Recherche</span>
      </Link>

      <button
        onClick={goToMessages}
        className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
          isMessagesActive
            ? 'bg-primary-emerald text-primary-emerald-foreground font-semibold'
            : 'text-muted-foreground hover:bg-surface-muted'
        }`}
      >
        <MessageCircle className="w-5 h-5" />
        <span className="font-sora text-[11px] mt-0.5">Messages</span>
      </button>

      <Link
        to="/profil"
        className={`flex flex-col items-center justify-center px-4 py-1.5 rounded-full transition-all ${
          pathname === '/profil'
            ? 'bg-primary-emerald text-primary-emerald-foreground font-semibold'
            : 'text-muted-foreground hover:bg-surface-muted'
        }`}
      >
        <User className="w-5 h-5" />
        <span className="font-sora text-[11px] mt-0.5">Profil</span>
      </Link>
    </nav>
  );
};
