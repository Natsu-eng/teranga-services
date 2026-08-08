import React from 'react';
import { ChevronLeft, Search, Briefcase } from 'lucide-react';
import { useLocation, useNavigate, type Location } from 'react-router';
import type { SignupRole } from '../../lib/api/auth-client';

interface RoleCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  tone: 'light' | 'pro';
  onSelect: () => void;
}

const RoleCard: React.FC<RoleCardProps> = ({ icon, title, description, tone, onSelect }) => (
  <button
    type="button"
    onClick={onSelect}
    className={`w-full text-left rounded-3xl p-6 flex items-start gap-4 border transition-all active:scale-[0.98] cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background ${
      tone === 'pro'
        ? 'bg-primary text-white border-primary artisan-shadow'
        : 'bg-white text-foreground border-border-subtle artisan-shadow hover:translate-y-[-2px] hover:shadow-md'
    }`}
  >
    <div
      className={`shrink-0 w-12 h-12 rounded-2xl flex items-center justify-center ${
        tone === 'pro' ? 'bg-white/15 text-white' : 'bg-primary-emerald/10 text-primary'
      }`}
    >
      {icon}
    </div>
    <div className="space-y-1">
      <h2 className="font-bold text-lg font-headline-md">{title}</h2>
      <p className={`text-sm ${tone === 'pro' ? 'text-primary-emerald-foreground' : 'text-muted-foreground'}`}>
        {description}
      </p>
    </div>
  </button>
);

/**
 * Choix du rôle à l'inscription (BUILD_PLAN.md §4) : deux espaces
 * distincts dès la première impression, la carte "artisan" reprenant déjà
 * l'identité visuelle `bg-primary` de l'Espace Pro (`ArtisanDashboardScreen`,
 * Header) pour préfigurer la distinction des deux espaces.
 */
export const RoleSelectScreen: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: Location } | null)?.from;

  const selectRole = (role: SignupRole) => {
    navigate('/connexion/nom', { state: { intent: 'signup', role, from } });
  };

  return (
    <main className="max-w-md mx-auto px-4 pt-16 pb-28 space-y-8">
      <button
        type="button"
        onClick={() => navigate('/connexion')}
        className="flex items-center gap-1 text-sm font-sora text-muted-foreground hover:text-foreground cursor-pointer"
      >
        <ChevronLeft className="w-4 h-4" />
        Retour
      </button>

      <div className="space-y-2">
        <h1 className="font-bold text-2xl text-primary">Créer un compte</h1>
        <p className="text-sm text-muted-foreground">
          Dites-nous qui vous êtes pour vous proposer la bonne expérience.
        </p>
      </div>

      <div className="space-y-4">
        <RoleCard
          icon={<Search className="w-6 h-6" />}
          title="Je cherche un artisan"
          description="Trouvez rapidement un artisan de confiance près de chez vous."
          tone="light"
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
    </main>
  );
};
