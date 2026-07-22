import { useCallback, useRef } from 'react';
import { useNavigate } from 'react-router';
import type { AppView } from '../types';

const VIEW_PATHS: Record<Exclude<AppView, 'artisan_profile' | 'chat'>, string> = {
  landing: '/',
  client_home: '/accueil',
  search: '/recherche',
  describe_problem: '/demande',
  artisan_dashboard: '/pro',
  profile: '/profil',
};

export function pathToView(pathname: string): AppView {
  if (pathname.startsWith('/artisans/')) return 'artisan_profile';
  if (pathname.startsWith('/messages/')) return 'chat';
  if (pathname === '/recherche') return 'search';
  if (pathname === '/pro') return 'artisan_dashboard';
  if (pathname === '/profil') return 'profile';
  if (pathname === '/demande') return 'describe_problem';
  return 'client_home';
}

// Bridges the legacy setCurrentView/setSelectedArtisanId callback pair onto
// real navigation while every screen is migrated one at a time. The selected
// id lives in a ref (not state) so that a setSelectedArtisanId() immediately
// followed by setCurrentView('artisan_profile' | 'chat') in the same handler
// always navigates to the id that was just selected, not a stale one.
export function useLegacyArtisanNavigation() {
  const navigate = useNavigate();
  const selectedArtisanIdRef = useRef<string | null>(null);

  const setSelectedArtisanId = useCallback((id: string) => {
    selectedArtisanIdRef.current = id;
  }, []);

  const setCurrentView = useCallback(
    (view: AppView) => {
      if (view === 'artisan_profile') {
        navigate(`/artisans/${selectedArtisanIdRef.current ?? ''}`);
        return;
      }
      if (view === 'chat') {
        navigate(`/messages/${selectedArtisanIdRef.current ?? ''}`);
        return;
      }
      navigate(VIEW_PATHS[view]);
    },
    [navigate],
  );

  return { setSelectedArtisanId, setCurrentView };
}
