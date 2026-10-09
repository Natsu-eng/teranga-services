import React from 'react';
import { Home, LayoutDashboard, MessageCircle, Search, User, type LucideIcon } from 'lucide-react';
import { NavLink } from 'react-router';
import { cn } from '../../lib/cn';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Actif uniquement sur l'URL exacte (sinon aussi sur ses sous-pages). */
  end?: boolean;
}

/*
 * Deux navigations volontairement distinctes, visuellement ET
 * structurellement : 4 entrées sur fond clair côté client, 3 entrées sur
 * le vert profond de l'espace Pro côté artisan.
 */
const CLIENT_ITEMS: NavItem[] = [
  { to: '/accueil', label: 'Accueil', icon: Home, end: true },
  { to: '/recherche', label: 'Recherche', icon: Search, end: true },
  { to: '/messages', label: 'Messages', icon: MessageCircle },
  { to: '/profil', label: 'Profil', icon: User, end: true },
];

const PRO_ITEMS: NavItem[] = [
  { to: '/pro', label: 'Tableau de bord', icon: LayoutDashboard, end: true },
  { to: '/messages', label: 'Messages', icon: MessageCircle },
  { to: '/profil', label: 'Profil', icon: User, end: true },
];

/** Barre de navigation client : surface claire, indicateur vert clair sur l'entrée active. */
export const ClientBottomNav: React.FC = () => (
  <nav
    aria-label="Navigation principale"
    className="fixed bottom-0 inset-x-0 z-40 bg-surface/95 backdrop-blur-md shadow-bar pb-safe"
  >
    <ul className="max-w-md mx-auto grid grid-cols-4 px-2 pt-2">
      {CLIENT_ITEMS.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={end}
            className="group flex flex-col items-center gap-1 py-1 rounded-field text-caption font-medium text-muted-foreground aria-[current=page]:text-primary aria-[current=page]:font-semibold"
          >
            <span className="inline-flex w-14 h-8 items-center justify-center rounded-full transition-colors group-hover:bg-surface-muted group-aria-[current=page]:bg-emerald-tint">
              <Icon aria-hidden className="w-5 h-5" />
            </span>
            {label}
          </NavLink>
        </li>
      ))}
    </ul>
  </nav>
);

/** Barre de navigation Pro : vert profond, indicateur or sur l'entrée active. */
export const ProBottomNav: React.FC = () => (
  <nav
    aria-label="Navigation de l'espace Pro"
    data-tone="dark"
    className="fixed bottom-0 inset-x-0 z-40 bg-primary text-white shadow-bar pb-safe"
  >
    <ul className="max-w-md mx-auto grid grid-cols-3 px-2 pt-2">
      {PRO_ITEMS.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={end}
            className={cn(
              'group flex flex-col items-center gap-1 py-1 rounded-field text-caption font-medium',
              'text-primary-emerald-foreground aria-[current=page]:text-white aria-[current=page]:font-semibold',
            )}
          >
            <span className="inline-flex w-14 h-8 items-center justify-center rounded-full transition-colors group-hover:bg-white/10 group-aria-[current=page]:bg-accent group-aria-[current=page]:text-primary">
              <Icon aria-hidden className="w-5 h-5" />
            </span>
            {label}
          </NavLink>
        </li>
      ))}
    </ul>
  </nav>
);
