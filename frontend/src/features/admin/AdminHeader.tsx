import React from 'react';
import { LogOut, ShieldCheck } from 'lucide-react';
import { NavLink } from 'react-router';
import { Button } from '../../components/ui/Button';
import { Logo } from '../../components/ui/Logo';
import { useAuth } from '../auth/hooks/useAuth';

/** Sections du back-office, dans l'ordre de la navigation. */
const ADMIN_SECTIONS = [
  { to: '/admin', label: 'Vue d’ensemble', end: true },
  { to: '/admin/verifications', label: 'Vérifications', end: false },
  { to: '/admin/artisans', label: 'Artisans', end: false },
  { to: '/admin/utilisateurs', label: 'Utilisateurs', end: false },
  { to: '/admin/avis', label: 'Avis', end: false },
  { to: '/admin/litiges', label: 'Litiges', end: false },
  { to: '/admin/support', label: 'Support', end: false },
  { to: '/admin/commissions', label: 'Commissions', end: false },
  { to: '/admin/journal', label: 'Journal', end: false },
] as const;

/**
 * En-tête du back-office : CLAIR et neutre, volontairement distinct du
 * bandeau vert de l'espace Pro. La navigation défile horizontalement sur
 * mobile plutôt que de passer à la ligne : les huit sections restent
 * atteignables d'un geste, la section courante est signalée par
 * `aria-current` (pas seulement par la couleur).
 */
export const AdminHeader: React.FC = () => {
  const auth = useAuth();
  return (
    <header className="sticky top-0 z-40 bg-surface shadow-card">
      <div className="max-w-5xl mx-auto flex items-center justify-between gap-3 h-16 px-4 md:px-8">
        <div className="flex items-center gap-2">
          <Logo />
          <span className="inline-flex items-center gap-1 rounded-md bg-foreground px-1.5 py-0.5 text-caption font-bold uppercase tracking-wider text-white">
            <ShieldCheck aria-hidden className="w-3.5 h-3.5" />
            Admin
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void auth.logout()}
          leadingIcon={<LogOut aria-hidden className="w-4 h-4" />}
        >
          Déconnexion
        </Button>
      </div>
      <nav aria-label="Sections admin" className="max-w-5xl mx-auto px-4 md:px-8 overflow-x-auto">
        <ul className="flex gap-4 whitespace-nowrap">
          {ADMIN_SECTIONS.map((section) => (
            <li key={section.to}>
              <NavLink
                to={section.to}
                end={section.end}
                className="inline-block py-2 text-sm font-medium text-muted-foreground border-b-2 border-transparent aria-[current=page]:border-primary-emerald aria-[current=page]:text-primary"
              >
                {section.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
};
