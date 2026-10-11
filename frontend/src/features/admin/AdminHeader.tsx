import React from 'react';
import { LogOut, ShieldCheck } from 'lucide-react';
import { NavLink } from 'react-router';
import { Button } from '../../components/ui/Button';
import { Logo } from '../../components/ui/Logo';
import { useAuth } from '../auth/hooks/useAuth';

const SECTIONS = [
  { to: '/admin/verifications', label: 'Vérifications' },
  { to: '/admin/litiges', label: 'Litiges' },
] as const;

/**
 * En-tête de l'espace admin : CLAIR et neutre, volontairement distinct du
 * bandeau vert de l'espace Pro, avec la navigation entre ses sections.
 */
export const AdminHeader: React.FC = () => {
  const auth = useAuth();
  return (
    <header className="sticky top-0 z-40 bg-surface shadow-card">
      <div className="max-w-3xl mx-auto flex items-center justify-between gap-3 h-16 px-4 md:px-8">
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
      <nav aria-label="Sections admin" className="max-w-3xl mx-auto px-4 md:px-8">
        <ul className="flex gap-4">
          {SECTIONS.map((section) => (
            <li key={section.to}>
              <NavLink
                to={section.to}
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
