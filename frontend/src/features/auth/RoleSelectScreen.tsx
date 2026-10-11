import React from 'react';
import { Briefcase, ChevronRight, Search } from 'lucide-react';
import { useLocation, useNavigate, type Location } from 'react-router';
import type { SignupRole } from '../../lib/api/auth-client';
import { cn } from '../../lib/cn';
import { cardClasses } from '../../components/ui/styles';
import { AuthShell } from './components/AuthShell';

interface RoleCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  tone: 'client' | 'pro';
  onSelect: () => void;
}

/**
 * Carte de choix de rôle. Les deux cartes préfigurent les deux espaces :
 * blanche pour le client, vert profond (la couleur du bandeau Pro) pour
 * l'artisan — même forme, même structure, identité distincte.
 */
const RoleCard: React.FC<RoleCardProps> = ({ icon, title, description, tone, onSelect }) => {
  const isPro = tone === 'pro';
  return (
    <button
      type="button"
      onClick={onSelect}
      data-tone={isPro ? 'dark' : undefined}
      className={cn(
        cardClasses({ tone: isPro ? 'dark' : 'default', padding: 'lg', interactive: true }),
        'w-full text-left flex items-center gap-4',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'shrink-0 inline-flex w-12 h-12 items-center justify-center rounded-2xl',
          isPro ? 'bg-accent text-primary' : 'bg-emerald-tint text-primary-emerald',
        )}
      >
        {icon}
      </span>
      <span className="flex-1 min-w-0 space-y-1">
        <span
          className={cn(
            'block font-display text-title font-semibold',
            isPro ? 'text-white' : 'text-foreground',
          )}
        >
          {title}
        </span>
        <span
          className={cn(
            'block text-sm',
            isPro ? 'text-primary-emerald-foreground' : 'text-muted-foreground',
          )}
        >
          {description}
        </span>
      </span>
      <ChevronRight
        aria-hidden
        className={cn('w-5 h-5 shrink-0', isPro ? 'text-accent' : 'text-primary-emerald')}
      />
    </button>
  );
};

/**
 * Choix du rôle à l'inscription (BUILD_PLAN.md §4) : deux espaces
 * distincts dès la première impression.
 */
export const RoleSelectScreen: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: Location } | null)?.from;

  const selectRole = (role: SignupRole) => {
    navigate('/connexion/nom', { state: { intent: 'signup', role, from } });
  };

  return (
    <AuthShell
      title="Créer un compte"
      description="Dites-nous qui vous êtes pour vous proposer la bonne expérience."
      onBack={() => navigate('/connexion')}
    >
      <div className="space-y-4">
        <RoleCard
          icon={<Search className="w-6 h-6" />}
          title="Je cherche un artisan"
          description="Trouvez rapidement un artisan de confiance près de chez vous."
          tone="client"
          onSelect={() => selectRole('client')}
        />
        <RoleCard
          icon={<Briefcase className="w-6 h-6" />}
          title="Je suis un artisan"
          description="Recevez des demandes de clients et développez votre activité."
          tone="pro"
          onSelect={() => selectRole('artisan')}
        />
      </div>
    </AuthShell>
  );
};
