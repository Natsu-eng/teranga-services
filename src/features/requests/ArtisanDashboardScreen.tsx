import React, { useState } from 'react';
import { TrendingUp, CheckCircle2, Star, Zap, MapPin, X, Send } from 'lucide-react';
import { AppView, JobRequest, Artisan } from '../../types';
import { SafeImage } from '../../components/ui/SafeImage';

interface ArtisanDashboardScreenProps {
  artisan: Artisan;
  jobRequests: JobRequest[];
  setJobRequests: React.Dispatch<React.SetStateAction<JobRequest[]>>;
  setCurrentView: (view: AppView) => void;
}

export const ArtisanDashboardScreen: React.FC<ArtisanDashboardScreenProps> = ({
  artisan: _artisan,
  jobRequests,
  setJobRequests,
  setCurrentView,
}) => {
  const [isAvailable, setIsAvailable] = useState<boolean>(true);
  const [selectedJob, setSelectedJob] = useState<JobRequest | null>(null);
  const [showQuoteModal, setShowQuoteModal] = useState<boolean>(false);
  const [laborPrice, setLaborPrice] = useState<number>(8000);
  const [materialsPrice, setMaterialsPrice] = useState<number>(4000);

  const handleSendQuote = () => {
    if (selectedJob) {
      setJobRequests((prev) =>
        prev.map((j) => (j.id === selectedJob.id ? { ...j, status: 'accepted' } : j)),
      );
      setShowQuoteModal(false);
      setSelectedJob(null);
      setCurrentView('chat');
    }
  };

  return (
    <main className="max-w-5xl mx-auto px-4 md:px-8 pt-4 pb-28 space-y-6">
      {/* Welcome & Availability Toggle */}
      <section className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="font-bold text-2xl md:text-3xl text-primary">Bonjour, Idrissa 👋</h2>
          <p className="text-muted-foreground text-sm md:text-base">
            Prêt pour vos services d&apos;aujourd&apos;hui ?
          </p>
        </div>

        {/* Switch Toggle */}
        <div className="flex items-center bg-surface-muted p-2 rounded-full border border-border-strong/30">
          <span
            className={`px-3 font-sora text-xs md:text-sm font-semibold transition-colors ${
              isAvailable ? 'text-primary' : 'text-muted-foreground-soft'
            }`}
          >
            {isAvailable ? 'Disponible' : 'Indisponible'}
          </span>

          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={isAvailable}
              onChange={(e) => setIsAvailable(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-border-strong peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-emerald" />
          </label>

          <span className="px-3 font-sora text-xs text-muted-foreground">En ligne</span>
        </div>
      </section>

      {/* Revenue & Stats Bento Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Main Revenue Card */}
        <div className="lg:col-span-8 bg-white p-6 md:p-8 rounded-2xl artisan-shadow flex flex-col justify-between border border-border-subtle relative overflow-hidden">
          <div className="absolute -right-12 -top-12 w-48 h-48 bg-primary/5 rounded-full blur-3xl"></div>

          <div>
            <span className="font-sora text-xs font-bold text-muted-foreground uppercase tracking-wider">
              REVENUS DU MOIS
            </span>
            <div className="mt-2 flex items-end gap-3 flex-wrap">
              <span className="font-bold text-3xl md:text-4xl text-primary">245 000 FCFA</span>
              <div className="flex items-center text-primary font-sora text-xs font-semibold mb-1">
                <TrendingUp className="w-[18px] h-[18px]" />
                <span className="ml-1">+12% vs mois dernier</span>
              </div>
            </div>
          </div>

          {/* Bar Chart */}
          <div className="mt-8 h-32 flex items-end gap-2.5">
            <div
              className="flex-1 bg-primary/10 rounded-t-md h-[40%]"
              title="Semaine 1: 45 000 FCFA"
            />
            <div
              className="flex-1 bg-primary/10 rounded-t-md h-[60%]"
              title="Semaine 2: 65 000 FCFA"
            />
            <div
              className="flex-1 bg-primary/10 rounded-t-md h-[45%]"
              title="Semaine 3: 50 000 FCFA"
            />
            <div
              className="flex-1 bg-primary/10 rounded-t-md h-[75%]"
              title="Semaine 4: 85 000 FCFA"
            />
            <div
              className="flex-1 bg-primary-emerald rounded-t-md h-[100%]"
              title="Cette semaine: 110 000 FCFA"
            />
          </div>
        </div>

        {/* Side Stats Column */}
        <div className="lg:col-span-4 flex flex-col gap-3">
          <div className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground font-sora text-xs font-medium">
                Demandes acceptées
              </span>
              <CheckCircle2 className="text-primary bg-primary/10 p-1.5 rounded-lg w-9 h-9" />
            </div>
            <span className="font-bold text-2xl text-primary mt-1 block">28</span>
          </div>

          <div className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground font-sora text-xs font-medium">Note moyenne</span>
              <div className="flex items-center bg-accent-soft text-accent-foreground-strong px-2 py-0.5 rounded-full">
                <Star className="w-[14px] h-[14px]" fill="currentColor" />
                <span className="ml-1 text-[11px] font-sora font-bold">Top Pro</span>
              </div>
            </div>
            <span className="font-bold text-2xl text-primary mt-1 block">4.9/5</span>
          </div>

          <div className="bg-white p-4 rounded-2xl artisan-shadow border border-border-subtle">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground font-sora text-xs font-medium">Taux de réponse</span>
              <Zap className="text-primary bg-primary/10 p-1.5 rounded-lg w-9 h-9" />
            </div>
            <span className="font-bold text-2xl text-primary mt-1 block">95%</span>
          </div>
        </div>
      </div>

      {/* New Requests Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-xl text-primary">Nouvelles demandes</h3>
          <span className="bg-primary-emerald text-white text-xs font-sora px-2.5 py-0.5 rounded-full font-bold">
            {jobRequests.length} en attente
          </span>
        </div>

        <div className="space-y-3">
          {jobRequests.map((req) => (
            <div
              key={req.id}
              className="bg-white p-5 rounded-2xl artisan-shadow border border-border-subtle flex flex-col md:flex-row items-start md:items-center justify-between gap-4 transition-all hover:border-primary/30"
            >
              <div className="flex items-center gap-4 w-full md:w-auto">
                <div className="w-12 h-12 rounded-full overflow-hidden shrink-0 border border-border">
                  <SafeImage
                    src={req.clientAvatar}
                    fallback="/images/placeholder-avatar.svg"
                    alt={req.clientName}
                    className="w-full h-full object-cover"
                  />
                </div>
                <div className="flex flex-col">
                  <h4 className="font-sora font-bold text-base text-foreground">{req.clientName}</h4>
                  <p className="text-sm text-muted-foreground font-medium">{req.title}</p>
                  <div className="flex items-center text-xs font-sora text-muted-foreground-soft mt-0.5">
                    <MapPin className="w-[14px] h-[14px] mr-1 text-primary" />
                    <span>{req.location}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between md:justify-end w-full md:w-auto gap-4">
                <span className="text-xs font-sora text-muted-foreground-soft italic">{req.timeAgo}</span>
                <button
                  onClick={() => {
                    setSelectedJob(req);
                    setShowQuoteModal(true);
                  }}
                  className="bg-accent text-white font-sora text-xs font-bold px-6 py-2.5 rounded-full hover:shadow-md active:scale-95 transition-all cursor-pointer"
                >
                  Voir
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Geolocation Optimization Banner */}
      <section className="bg-primary text-white rounded-2xl overflow-hidden relative p-6 md:p-8 flex items-center shadow-lg">
        <div className="relative z-10 max-w-md space-y-3">
          <h3 className="font-bold text-xl md:text-2xl">Optimisez vos interventions</h3>
          <p className="text-sm opacity-90 leading-relaxed font-sora">
            Grâce à notre nouveau système de géolocalisation à Dakar, recevez des demandes encore
            plus proches de votre position actuelle.
          </p>
          <button
            onClick={() => alert('Géolocalisation activée sur Dakar Plateau & Almadies')}
            className="bg-white text-primary px-6 py-2.5 rounded-full font-sora text-xs font-bold hover:bg-surface-muted transition-colors cursor-pointer"
          >
            En savoir plus
          </button>
        </div>
      </section>

      {/* Quote Proposal Modal */}
      {showQuoteModal && selectedJob && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-5 shadow-2xl relative">
            <button
              onClick={() => setShowQuoteModal(false)}
              className="absolute top-4 right-4 text-muted-foreground-soft hover:text-foreground"
            >
              <X className="w-6 h-6" />
            </button>

            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full overflow-hidden">
                <SafeImage
                  src={selectedJob.clientAvatar}
                  fallback="/images/placeholder-avatar.svg"
                  alt={selectedJob.clientName}
                  className="w-full h-full object-cover"
                />
              </div>
              <div>
                <h3 className="font-bold text-lg text-primary">{selectedJob.clientName}</h3>
                <p className="text-xs font-sora text-muted-foreground-soft">{selectedJob.location}</p>
              </div>
            </div>

            <div className="bg-surface-muted p-4 rounded-2xl border border-border">
              <p className="font-bold text-sm text-foreground mb-1">{selectedJob.title}</p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                &quot;{selectedJob.description || 'Besoin d intervention en urgence.'}&quot;
              </p>
            </div>

            <div className="space-y-3">
              <h4 className="font-sora text-xs font-bold text-primary uppercase tracking-wider">
                Rédiger un Devis
              </h4>

              <div className="space-y-2">
                <div>
                  <label className="text-xs font-sora text-muted-foreground font-semibold">
                    Main d&apos;œuvre (FCFA)
                  </label>
                  <input
                    type="number"
                    value={laborPrice}
                    onChange={(e) => setLaborPrice(Number(e.target.value))}
                    className="w-full p-3 rounded-xl border border-border-strong text-sm mt-1 outline-none focus:border-primary"
                  />
                </div>

                <div>
                  <label className="text-xs font-sora text-muted-foreground font-semibold">
                    Fournitures (FCFA)
                  </label>
                  <input
                    type="number"
                    value={materialsPrice}
                    onChange={(e) => setMaterialsPrice(Number(e.target.value))}
                    className="w-full p-3 rounded-xl border border-border-strong text-sm mt-1 outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div className="flex justify-between items-center bg-primary/10 p-3.5 rounded-xl font-sora">
                <span className="font-bold text-sm text-primary">Total Devis</span>
                <span className="font-bold text-lg text-primary">
                  {(laborPrice + materialsPrice).toLocaleString()} FCFA
                </span>
              </div>
            </div>

            <button
              onClick={handleSendQuote}
              className="w-full py-4 rounded-full bg-primary text-white font-sora text-sm font-bold shadow-lg hover:brightness-110 active:scale-95 transition-all cursor-pointer flex items-center justify-center gap-2"
            >
              <span>Envoyer le devis au client</span>
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </main>
  );
};
