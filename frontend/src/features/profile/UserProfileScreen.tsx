import React, { useState } from 'react';
import { CheckCircle, ClipboardList, CreditCard, LogOut } from 'lucide-react';
import { Link, useNavigate } from 'react-router';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { useArtisan } from '../artisans/hooks/useArtisan';
import { useCurrentUser } from './hooks/useCurrentUser';

interface UserProfileScreenProps {
  location: string;
}

export const UserProfileScreen: React.FC<UserProfileScreenProps> = ({ location }) => {
  const navigate = useNavigate();
  const auth = useAuth();
  const userRole = toDisplayRole(auth.role);
  const { data: currentUser, isLoading, error, reload } = useCurrentUser();
  const { data: proArtisan } = useArtisan(userRole === 'artisan' ? currentUser?.artisanId ?? null : null);
  const [paymentMethod, setPaymentMethod] = useState<'wave' | 'om' | 'card'>('wave');

  const handleLogout = async () => {
    await auth.logout();
    navigate('/');
  };

  return (
    <main className="max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-28 space-y-6">
      {/* User Header */}
      {isLoading && !currentUser ? (
        <div className="bg-white p-6 rounded-3xl artisan-shadow border border-border-subtle flex items-center gap-4">
          <Skeleton className="w-16 h-16 rounded-full shrink-0" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-3 w-24" />
          </div>
        </div>
      ) : error && !currentUser ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : currentUser ? (
        <div className="bg-white p-6 rounded-3xl artisan-shadow border border-border-subtle flex items-center gap-4">
          <div className="w-16 h-16 rounded-full bg-primary text-primary-emerald-foreground font-bold font-sora text-xl flex items-center justify-center border-2 border-primary-emerald">
            {currentUser.initials}
          </div>
          <div className="flex-1">
            <h2 className="font-bold text-xl text-primary">{currentUser.name}</h2>
            <p className="text-xs font-sora text-muted-foreground-soft">{location}</p>
            {currentUser.verified && (
              <span className="inline-block mt-1 px-2.5 py-0.5 rounded-full bg-accent-soft/50 text-accent-foreground font-sora text-[11px] font-bold">
                Membre Téranga Vérifié
              </span>
            )}
          </div>
        </div>
      ) : null}

      {/* Mode : dérivé du compte connecté (auth.role), plus un choix client — corrige le point d'audit du toggle auto-déclaré. */}
      <div className="bg-surface-muted p-4 rounded-2xl border border-border">
        <h4 className="font-bold text-sm text-foreground">Mode actuel</h4>
        <p className="text-xs font-sora text-muted-foreground-soft">
          {userRole === 'client'
            ? 'Espace Client (Demandes de services)'
            : `Espace Artisan Pro${proArtisan ? ` (${proArtisan.name})` : ''}`}
        </p>
      </div>

      {/* Client-only entry point to their service_request history (Lot 12). */}
      {userRole === 'client' && (
        <Link
          to="/mes-demandes"
          className="flex items-center justify-between bg-white p-4 rounded-3xl artisan-shadow border border-border-subtle cursor-pointer hover:shadow-md transition-all"
        >
          <div className="flex items-center gap-3">
            <ClipboardList className="text-primary w-6 h-6" />
            <span className="font-sora text-sm font-semibold text-foreground">Mes demandes</span>
          </div>
        </Link>
      )}

      {/* Payment Options (Senegal preferred) */}
      <div className="bg-white p-6 rounded-3xl artisan-shadow border border-border-subtle space-y-4">
        <h3 className="font-bold text-base text-primary">Moyens de paiement au Sénégal</h3>

        <div className="space-y-2">
          <label
            onClick={() => setPaymentMethod('wave')}
            className={`flex items-center justify-between p-3.5 rounded-2xl border cursor-pointer transition-all ${
              paymentMethod === 'wave'
                ? 'border-primary bg-primary/5 font-bold'
                : 'border-border text-muted-foreground'
            }`}
          >
            <div className="flex items-center gap-3">
              <span className="w-8 h-8 rounded-full bg-brand-wave text-white font-bold text-xs flex items-center justify-center">
                W
              </span>
              <span className="text-sm font-sora">Wave Sénégal</span>
            </div>
            {paymentMethod === 'wave' && (
              <CheckCircle className="text-primary w-6 h-6" />
            )}
          </label>

          <label
            onClick={() => setPaymentMethod('om')}
            className={`flex items-center justify-between p-3.5 rounded-2xl border cursor-pointer transition-all ${
              paymentMethod === 'om'
                ? 'border-primary bg-primary/5 font-bold'
                : 'border-border text-muted-foreground'
            }`}
          >
            <div className="flex items-center gap-3">
              <span className="w-8 h-8 rounded-full bg-brand-orange-money text-white font-bold text-xs flex items-center justify-center">
                OM
              </span>
              <span className="text-sm font-sora">Orange Money Sénégal</span>
            </div>
            {paymentMethod === 'om' && (
              <CheckCircle className="text-primary w-6 h-6" />
            )}
          </label>

          <label
            onClick={() => setPaymentMethod('card')}
            className={`flex items-center justify-between p-3.5 rounded-2xl border cursor-pointer transition-all ${
              paymentMethod === 'card'
                ? 'border-primary bg-primary/5 font-bold'
                : 'border-border text-muted-foreground'
            }`}
          >
            <div className="flex items-center gap-3">
              <CreditCard className="text-primary w-6 h-6" />
              <span className="text-sm font-sora">Carte bancaire internationale</span>
            </div>
            {paymentMethod === 'card' && (
              <CheckCircle className="text-primary w-6 h-6" />
            )}
          </label>
        </div>
      </div>

      {/* Account actions */}
      <div className="bg-white p-4 rounded-3xl artisan-shadow border border-border-subtle space-y-1">
        <button
          onClick={handleLogout}
          className="w-full text-left px-4 py-3 text-sm font-sora text-destructive font-semibold flex items-center gap-2 hover:bg-destructive-soft/20 rounded-xl transition-colors cursor-pointer"
        >
          <LogOut className="w-6 h-6" />
          <span>Déconnexion</span>
        </button>
      </div>
    </main>
  );
};
