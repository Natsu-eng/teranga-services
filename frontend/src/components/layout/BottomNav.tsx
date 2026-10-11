import React from 'react';
import { Home, LayoutDashboard, MessageCircle, Search, User, type LucideIcon } from 'lucide-react';
import { NavLink } from 'react-router';
import { useRealtime } from '../../features/messages/realtime/useRealtime';
import { cn } from '../../lib/cn';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Actif uniquement sur l'URL exacte (sinon aussi sur ses sous-pages). */
  end?: boolean;
  /** Affiche le nombre de messages non lus (entrée « Messages »). */
  showsUnread?: boolean;
}

/*
 * Deux navigations volontairement distinctes, visuellement ET
 * structurellement : 4 entrées sur fond clair côté client, 3 entrées sur
 * le vert profond de l'espace Pro côté artisan.
 */
const CLIENT_ITEMS: NavItem[] = [
  { to: '/accueil', label: 'Accueil', icon: Home, end: true },
  { to: '/recherche', label: 'Recherche', icon: Search, end: true },
  { to: '/messages', label: 'Messages', icon: MessageCircle, showsUnread: true },
  { to: '/profil', label: 'Profil', icon: User, end: true },
];

const PRO_ITEMS: NavItem[] = [
  { to: '/pro', label: 'Tableau de bord', icon: LayoutDashboard, end: true },
  { to: '/messages', label: 'Messages', icon: MessageCircle, showsUnread: true },
  { to: '/profil', label: 'Profil', icon: User, end: true },
];

/** Au-delà, la pastille affiche « 99+ » (le nombre exact reste lu à voix haute). */
const MAX_DISPLAYED_UNREAD = 99;

/**
 * Pastille de non-lus, en or (accent du design system) sur les deux
 * navigations. Purement visuelle : elle est posée sur l'icône, donc avant
 * le libellé dans le DOM ; le nombre exact est annoncé séparément par
 * `UnreadLabel`, placé après le libellé (« Messages, 3 non lus »).
 */
const UnreadPill: React.FC<{ count: number }> = ({ count }) => (
  <span
    aria-hidden
    className="absolute -top-1 right-1.5 inline-flex min-w-5 h-5 items-center justify-center rounded-full bg-accent px-1 text-caption font-bold text-primary ring-2 ring-surface"
  >
    {count > MAX_DISPLAYED_UNREAD ? `${MAX_DISPLAYED_UNREAD}+` : count}
  </span>
);

/** Complément du nom accessible du lien : nombre exact de non-lus. */
const UnreadLabel: React.FC<{ count: number }> = ({ count }) => (
  <span className="sr-only">
    , {count} non lu{count > 1 ? 's' : ''}
  </span>
);

/** Barre de navigation client : surface claire, indicateur vert clair sur l'entrée active. */
export const ClientBottomNav: React.FC = () => {
  const { unreadCount } = useRealtime();
  return (
    <nav
      aria-label="Navigation principale"
      className="fixed bottom-0 inset-x-0 z-40 bg-surface/95 backdrop-blur-md shadow-bar pb-safe"
    >
      <ul className="max-w-md mx-auto grid grid-cols-4 px-2 pt-2">
        {CLIENT_ITEMS.map(({ to, label, icon: Icon, end, showsUnread }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              className="group flex flex-col items-center gap-1 py-1 rounded-field text-caption font-medium text-muted-foreground aria-[current=page]:text-primary aria-[current=page]:font-semibold"
            >
              <span className="relative inline-flex w-14 h-8 items-center justify-center rounded-full transition-colors group-hover:bg-surface-muted group-aria-[current=page]:bg-emerald-tint">
                <Icon aria-hidden className="w-5 h-5" />
                {showsUnread && !!unreadCount && <UnreadPill count={unreadCount} />}
              </span>
              {label}
              {showsUnread && !!unreadCount && <UnreadLabel count={unreadCount} />}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
};

/** Barre de navigation Pro : vert profond, indicateur or sur l'entrée active. */
export const ProBottomNav: React.FC = () => {
  const { unreadCount } = useRealtime();
  return (
    <nav
      aria-label="Navigation de l'espace Pro"
      data-tone="dark"
      className="fixed bottom-0 inset-x-0 z-40 bg-primary text-white shadow-bar pb-safe"
    >
      <ul className="max-w-md mx-auto grid grid-cols-3 px-2 pt-2">
        {PRO_ITEMS.map(({ to, label, icon: Icon, end, showsUnread }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              className={cn(
                'group flex flex-col items-center gap-1 py-1 rounded-field text-caption font-medium',
                'text-primary-emerald-foreground aria-[current=page]:text-white aria-[current=page]:font-semibold',
              )}
            >
              <span className="relative inline-flex w-14 h-8 items-center justify-center rounded-full transition-colors group-hover:bg-white/10 group-aria-[current=page]:bg-accent group-aria-[current=page]:text-primary">
                <Icon aria-hidden className="w-5 h-5" />
                {showsUnread && !!unreadCount && <UnreadPill count={unreadCount} />}
              </span>
              {label}
              {showsUnread && !!unreadCount && <UnreadLabel count={unreadCount} />}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
};
