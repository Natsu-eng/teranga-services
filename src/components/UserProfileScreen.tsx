import React, { useState } from 'react';
import { CheckCircle, CreditCard, LogOut } from 'lucide-react';
import { AppView, UserRole } from '../types';

interface UserProfileScreenProps {
  userRole: UserRole;
  setUserRole: (role: UserRole) => void;
  setCurrentView: (view: AppView) => void;
  location: string;
}

export const UserProfileScreen: React.FC<UserProfileScreenProps> = ({
  userRole,
  setUserRole,
  setCurrentView,
  location,
}) => {
  const [paymentMethod, setPaymentMethod] = useState<'wave' | 'om' | 'card'>('wave');

  return (
    <main className="max-w-3xl mx-auto px-4 md:px-8 pt-4 pb-28 space-y-6">
      {/* User Header */}
      <div className="bg-white p-6 rounded-3xl artisan-shadow border border-[#eae7e7] flex items-center gap-4">
        <div className="w-16 h-16 rounded-full bg-[#004129] text-[#8acfa9] font-bold font-sora text-xl flex items-center justify-center border-2 border-[#0e5a3c]">
          DD
        </div>
        <div className="flex-1">
          <h2 className="font-bold text-xl text-[#004129]">Diandé Diallo</h2>
          <p className="text-xs font-sora text-[#707972]">{location}</p>
          <span className="inline-block mt-1 px-2.5 py-0.5 rounded-full bg-[#ffddb1]/50 text-[#815600] font-sora text-[11px] font-bold">
            Membre Téranga Vérifié
          </span>
        </div>
      </div>

      {/* Role Switcher */}
      <div className="bg-[#f6f3f2] p-4 rounded-2xl border border-[#e5e2e1] flex justify-between items-center">
        <div>
          <h4 className="font-bold text-sm text-[#1c1b1b]">Mode actuel</h4>
          <p className="text-xs font-sora text-[#707972]">
            {userRole === 'client'
              ? 'Espace Client (Demandes de services)'
              : 'Espace Artisan Pro (Idrissa Diop)'}
          </p>
        </div>
        <button
          onClick={() => {
            const next = userRole === 'client' ? 'artisan' : 'client';
            setUserRole(next);
            setCurrentView(next === 'artisan' ? 'artisan_dashboard' : 'client_home');
          }}
          className="bg-[#004129] text-white px-4 py-2 rounded-full font-sora text-xs font-bold hover:opacity-90 transition-all cursor-pointer"
        >
          Bascule vers {userRole === 'client' ? 'Pro' : 'Client'}
        </button>
      </div>

      {/* Payment Options (Senegal preferred) */}
      <div className="bg-white p-6 rounded-3xl artisan-shadow border border-[#eae7e7] space-y-4">
        <h3 className="font-bold text-base text-[#004129]">Moyens de paiement au Sénégal</h3>

        <div className="space-y-2">
          <label
            onClick={() => setPaymentMethod('wave')}
            className={`flex items-center justify-between p-3.5 rounded-2xl border cursor-pointer transition-all ${
              paymentMethod === 'wave'
                ? 'border-[#004129] bg-[#004129]/5 font-bold'
                : 'border-[#e5e2e1] text-[#404943]'
            }`}
          >
            <div className="flex items-center gap-3">
              <span className="w-8 h-8 rounded-full bg-[#1dc8f0] text-white font-bold text-xs flex items-center justify-center">
                W
              </span>
              <span className="text-sm font-sora">Wave Sénégal</span>
            </div>
            {paymentMethod === 'wave' && (
              <CheckCircle className="text-[#004129] w-6 h-6" />
            )}
          </label>

          <label
            onClick={() => setPaymentMethod('om')}
            className={`flex items-center justify-between p-3.5 rounded-2xl border cursor-pointer transition-all ${
              paymentMethod === 'om'
                ? 'border-[#004129] bg-[#004129]/5 font-bold'
                : 'border-[#e5e2e1] text-[#404943]'
            }`}
          >
            <div className="flex items-center gap-3">
              <span className="w-8 h-8 rounded-full bg-[#ff6600] text-white font-bold text-xs flex items-center justify-center">
                OM
              </span>
              <span className="text-sm font-sora">Orange Money Sénégal</span>
            </div>
            {paymentMethod === 'om' && (
              <CheckCircle className="text-[#004129] w-6 h-6" />
            )}
          </label>

          <label
            onClick={() => setPaymentMethod('card')}
            className={`flex items-center justify-between p-3.5 rounded-2xl border cursor-pointer transition-all ${
              paymentMethod === 'card'
                ? 'border-[#004129] bg-[#004129]/5 font-bold'
                : 'border-[#e5e2e1] text-[#404943]'
            }`}
          >
            <div className="flex items-center gap-3">
              <CreditCard className="text-[#004129] w-6 h-6" />
              <span className="text-sm font-sora">Carte bancaire internationale</span>
            </div>
            {paymentMethod === 'card' && (
              <CheckCircle className="text-[#004129] w-6 h-6" />
            )}
          </label>
        </div>
      </div>

      {/* Account actions */}
      <div className="bg-white p-4 rounded-3xl artisan-shadow border border-[#eae7e7] space-y-1">
        <button
          onClick={() => setCurrentView('landing')}
          className="w-full text-left px-4 py-3 text-sm font-sora text-[#ba1a1a] font-semibold flex items-center gap-2 hover:bg-[#ffdad6]/20 rounded-xl transition-colors cursor-pointer"
        >
          <LogOut className="w-6 h-6" />
          <span>Déconnexion / Retour à l&apos;accueil</span>
        </button>
      </div>
    </main>
  );
};
