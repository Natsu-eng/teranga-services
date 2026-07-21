import React from 'react';
import { ArrowRight, BadgeCheck, HeartHandshake, Star } from 'lucide-react';
import { AppView, UserRole } from '../types';

interface LandingScreenProps {
  setCurrentView: (view: AppView) => void;
  setUserRole: (role: UserRole) => void;
}

export const LandingScreen: React.FC<LandingScreenProps> = ({ setCurrentView, setUserRole }) => {
  return (
    <div className="bg-[#fcf9f8] text-[#1c1b1b] min-h-screen flex flex-col overflow-x-hidden">
      {/* Hero Illustration Section */}
      <section className="relative w-full h-[55vh] md:h-[62vh] overflow-hidden">
        <div className="absolute inset-0 w-full h-full">
          <img
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuDSWS3RQlIfQFCLxRes3Jso743rGlk-MaehrAFtGoxxswhtCnRKGj__mENisENX-daqX9uyGzBKNmncgseeRP8PEj299BecKyOH0-2sFeW82iBKU3x8_G6S-tPUtarmOVkPptLwut2WJRsa4BCLA6spgnyuZlxgSfnuPmSsUCYjApid2NgdnT0Hdc5gQfPRPg33KG7xkwRsRo52kvfxMh5KI--ONt2tEOib8DBmARdGimA3agR5Uh9NtnfOoooVkftPTg6ey1DX9YUM"
            alt="Téranga Services Artisan"
            className="w-full h-full object-cover object-top scale-105 transition-transform duration-[3s] ease-out hover:scale-100"
          />
          <div className="absolute inset-0 hero-gradient"></div>
        </div>

        {/* Branding Float Header */}
        <div className="absolute top-6 left-0 w-full px-4 md:px-12 z-10 flex justify-between items-center">
          <div className="font-bold text-xl md:text-2xl text-[#004129] flex items-center gap-2">
            <span className="w-8 h-8 bg-[#004129] rounded-lg flex items-center justify-center text-white text-sm font-bold">
              T
            </span>
            <span>Téranga Services</span>
          </div>

          <div className="bg-white/80 backdrop-blur-sm px-4 py-2 rounded-full shadow-sm flex items-center gap-2 border border-[#bfc9c1]/30">
            <span className="w-2.5 h-2.5 rounded-full bg-[#815600] animate-pulse"></span>
            <span className="font-sora text-xs text-[#404943] font-medium">250+ Artisans Pro</span>
          </div>
        </div>
      </section>

      {/* Main Content Card */}
      <main className="flex-grow px-4 md:px-12 -mt-16 md:-mt-24 relative z-20 max-w-4xl mx-auto w-full flex flex-col items-center">
        <div className="w-full bg-[#fcf9f8] p-6 md:p-10 rounded-[32px] shadow-[0px_4px_20px_rgba(14,90,60,0.06)] text-center border border-[#e5e2e1]">
          <div className="mb-4 flex justify-center">
            <span className="px-4 py-1.5 rounded-full bg-[#ffddb1]/40 text-[#815600] font-sora text-xs font-semibold uppercase tracking-wider">
              L&apos;excellence au Sénégal
            </span>
          </div>

          <h1 className="font-headline-lg text-2xl md:text-4xl font-bold text-[#1c1b1b] mb-4 leading-tight max-w-lg mx-auto">
            Un artisan de confiance, en quelques secondes
          </h1>

          <p className="text-base md:text-lg text-[#404943] mb-8 max-w-md mx-auto leading-relaxed">
            La première plateforme sénégalaise pour vos services à domicile. Qualité, ponctualité et
            respect assurés.
          </p>

          <div className="flex flex-col gap-3 items-center w-full max-w-xs mx-auto">
            <button
              onClick={() => {
                setUserRole('client');
                setCurrentView('client_home');
              }}
              className="w-full bg-[#0e5a3c] text-white font-sora text-sm font-semibold py-4 rounded-full shadow-lg hover:brightness-110 active:scale-95 transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer"
            >
              <span>Commencer</span>
              <ArrowRight className="w-5 h-5" />
            </button>

            <button
              onClick={() => {
                setUserRole('artisan');
                setCurrentView('artisan_dashboard');
              }}
              className="w-full py-3 text-[#004129] font-sora text-sm font-semibold hover:underline decoration-2 underline-offset-4 transition-all cursor-pointer"
            >
              Vous êtes artisan ?
            </button>
          </div>
        </div>

        {/* Trust Indicators */}
        <div className="mt-8 w-full grid grid-cols-1 md:grid-cols-3 gap-4 pb-12">
          <div className="flex items-center gap-4 p-4 rounded-2xl bg-white/60 border border-[#bfc9c1]/20 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-[#004129]/10 flex items-center justify-center text-[#004129]">
              <BadgeCheck className="w-6 h-6" fill="currentColor" />
            </div>
            <div>
              <h3 className="font-sora text-sm font-bold text-[#1c1b1b]">Vérifiés</h3>
              <p className="font-sora text-xs text-[#404943]">Profils authentifiés</p>
            </div>
          </div>

          <div className="flex items-center gap-4 p-4 rounded-2xl bg-white/60 border border-[#bfc9c1]/20 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-[#004129]/10 flex items-center justify-center text-[#004129]">
              <HeartHandshake className="w-6 h-6" fill="currentColor" />
            </div>
            <div>
              <h3 className="font-sora text-sm font-bold text-[#1c1b1b]">Sécurisé</h3>
              <p className="font-sora text-xs text-[#404943]">Paiement protégé</p>
            </div>
          </div>

          <div className="flex items-center gap-4 p-4 rounded-2xl bg-white/60 border border-[#bfc9c1]/20 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-[#004129]/10 flex items-center justify-center text-[#004129]">
              <Star className="w-6 h-6" fill="currentColor" />
            </div>
            <div>
              <h3 className="font-sora text-sm font-bold text-[#1c1b1b]">Qualité 4.8/5</h3>
              <p className="font-sora text-xs text-[#404943]">Avis de nos clients</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
