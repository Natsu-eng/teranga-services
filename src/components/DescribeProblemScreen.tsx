import React, { useState } from 'react';
import { AppView, AIAnalysisResult, Artisan } from '../types';

interface DescribeProblemScreenProps {
  setCurrentView: (view: AppView) => void;
  setSelectedArtisan: (artisan: Artisan) => void;
  artisans: Artisan[];
}

export const DescribeProblemScreen: React.FC<DescribeProblemScreenProps> = ({
  setCurrentView,
  setSelectedArtisan,
  artisans,
}) => {
  const [description, setDescription] = useState<string>(
    "Le robinet de la cuisine fuit abondamment sous l'évier. L'eau s'écoule au niveau du joint du siphon depuis ce matin."
  );
  const [photoPreview, setPhotoPreview] = useState<string | null>(
    'https://lh3.googleusercontent.com/aida-public/AB6AXuCGgzVx_uIx917S-4xxo10zzmw2zvQkqiMbl173RPqwHI7CaCPLhBSFBcjReSz832uWiMs8IWf0ddCVzDx15jw97HDGQmd6lEXZUzdi3819jXNOhD1zVe6kH-OhzcN6yPfBhuEZPqhLhBgzsV3NwXIZH4Ajnj-ZzgJTOF6rMij9LLHr1FEHzYlmJ-KO6BNu4vDIsh94XU5yf3mxTw8fUk_VvNpL3Bv_Zxrm1YEkNs3YJq4cvysu-4_9xT2iMzHzyMaF3RBwZAH5dcTZ'
  );
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [recordingTime, setRecordingTime] = useState<number>(0);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);

  const [aiResult, setAiResult] = useState<AIAnalysisResult>({
    trade: 'Plomberie — fuite',
    priceEstimate: '8 000 – 15 000 FCFA',
    recommendedCount: 3,
    explanation: "L'IA a analysé votre description pour identifier les meilleurs experts disponibles immédiatement à Dakar.",
    urgency: 'haute',
    suggestedDevis: {
      title: "Réparation de fuite d'évier",
      labor: 8000,
      materials: 4000,
      total: 12000,
    },
  });

  // Handle Photo File Upload
  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const url = URL.createObjectURL(file);
      setPhotoPreview(url);
    }
  };

  // Handle Recording Simulation
  const toggleRecording = () => {
    if (!isRecording) {
      setIsRecording(true);
      setRecordingTime(0);
      const timer = setInterval(() => {
        setRecordingTime((prev) => {
          if (prev >= 10) {
            clearInterval(timer);
            setIsRecording(false);
            setDescription(
              (d) => d + " [Note vocale 0:10]: 'J'ai aussi une forte odeur d'humidité sous le meuble de cuisine.'"
            );
            return 10;
          }
          return prev + 1;
        });
      }, 1000);
    } else {
      setIsRecording(false);
    }
  };

  // Perform AI Analysis via Server Endpoint
  const triggerAiAnalysis = async (text: string) => {
    setIsAnalyzing(true);
    try {
      const res = await fetch('/api/analyze-problem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: text }),
      });
      if (res.ok) {
        const data = await res.json();
        setAiResult({
          trade: data.trade || 'Plomberie — fuite',
          priceEstimate: data.priceEstimate || '8 000 – 15 000 FCFA',
          recommendedCount: data.recommendedCount || 3,
          explanation:
            data.explanation ||
            "L'IA a analysé votre description pour identifier les meilleurs experts disponibles immédiatement à Dakar.",
          urgency: data.urgency || 'moyenne',
          suggestedDevis: data.suggestedDevis || {
            title: "Réparation de fuite d'eau",
            labor: 8000,
            materials: 4000,
            total: 12000,
          },
        });
      }
    } catch (err) {
      console.error('AI Analysis failed, using fallback:', err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#fcf9f8] text-[#1c1b1b] flex flex-col pb-32">
      {/* Top Bar */}
      <header className="sticky top-0 z-50 flex items-center h-16 px-4 bg-[#fcf9f8]/85 backdrop-blur-md border-b border-[#e5e2e1]">
        <button
          onClick={() => setCurrentView('client_home')}
          className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-[#f6f3f2] transition-colors active:scale-95 cursor-pointer"
        >
          <span className="material-symbols-outlined text-[#1c1b1b]">arrow_back</span>
        </button>
        <h1 className="ml-3 font-bold text-lg md:text-xl text-[#004129]">Décrivez votre problème</h1>
      </header>

      <main className="flex-1 max-w-2xl mx-auto w-full px-4 pt-4 space-y-6">
        {/* Input Textarea & Counter */}
        <section className="space-y-3">
          <div className="relative">
            <textarea
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                if (e.target.value.length > 10) {
                  triggerAiAnalysis(e.target.value);
                }
              }}
              maxLength={500}
              placeholder="Expliquez-nous ce qui ne va pas (ex: fuite d'eau, climatiseur qui ne refroidit plus)..."
              className="w-full h-40 p-4 rounded-2xl bg-white border border-[#bfc9c1] focus:border-[#004129] focus:ring-1 focus:ring-[#004129] text-base text-[#1c1b1b] placeholder:text-[#707972] transition-all resize-none shadow-sm outline-none"
            />
            <div className="absolute bottom-3 right-3 text-xs text-[#707972] font-sora">
              {description.length} / 500
            </div>
          </div>

          {/* Photo Preview if attached */}
          {photoPreview && (
            <div className="relative w-full h-28 rounded-2xl overflow-hidden border border-[#e5e2e1] group">
              <img src={photoPreview} alt="Aperçu fuite" className="w-full h-full object-cover" />
              <button
                onClick={() => setPhotoPreview(null)}
                className="absolute top-2 right-2 bg-black/60 text-white rounded-full p-1 hover:bg-black transition-colors"
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
              <div className="absolute bottom-2 left-2 bg-black/50 backdrop-blur-sm text-white px-2.5 py-0.5 rounded-full text-xs font-sora">
                Photo jointe
              </div>
            </div>
          )}

          {/* Media Action Buttons */}
          <div className="flex gap-3">
            <label className="flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-full border-1.5 border-[#004129] text-[#004129] font-sora text-xs font-bold hover:bg-[#004129]/5 active:scale-95 transition-all cursor-pointer">
              <span className="material-symbols-outlined text-[20px]">photo_camera</span>
              <span>Ajouter une photo</span>
              <input type="file" accept="image/*" onChange={handlePhotoUpload} className="hidden" />
            </label>

            <button
              onClick={toggleRecording}
              className={`flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-full border-1.5 border-[#004129] font-sora text-xs font-bold transition-all cursor-pointer ${
                isRecording
                  ? 'bg-[#ba1a1a] text-white border-[#ba1a1a] animate-pulse'
                  : 'text-[#004129] hover:bg-[#004129]/5 active:scale-95'
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">
                {isRecording ? 'mic_active' : 'mic'}
              </span>
              <span>{isRecording ? `Enregistrement 0:0${recordingTime}` : 'Message vocal'}</span>
            </button>
          </div>
        </section>

        {/* AI Analysis Result Card */}
        <section className="animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="magic-card-glow bg-white rounded-2xl p-6 relative overflow-hidden">
            {/* Ambient Shader Accent */}
            <div className="absolute -top-12 -right-12 w-32 h-32 bg-[#abf2ca] opacity-20 rounded-full blur-2xl"></div>

            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[#0e5a3c] fill-icon">auto_awesome</span>
                <h2 className="font-sora text-xs font-bold text-[#004129] tracking-wider uppercase">
                  ANALYSE TERMINÉE
                </h2>
              </div>
              {isAnalyzing && (
                <span className="text-xs font-sora text-[#815600] animate-pulse flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-[#815600] animate-ping" />
                  Mise à jour IA...
                </span>
              )}
            </div>

            <div className="space-y-4">
              <div>
                <p className="text-[#404943] font-sora text-[11px] font-bold uppercase mb-1">
                  Métier détecté
                </p>
                <p className="font-bold text-xl md:text-2xl text-[#0e5a3c]">{aiResult.trade}</p>
              </div>

              <div className="flex justify-between items-end border-t border-[#f0eded] pt-4">
                <div>
                  <p className="text-[#404943] font-sora text-[11px] font-bold uppercase mb-1">
                    Prix estimé
                  </p>
                  <p className="font-bold text-lg text-[#1c1b1b]">{aiResult.priceEstimate}</p>
                  <span className="text-[10px] text-[#707972] italic block mt-0.5">
                    (Estimation basée sur des cas similaires à Dakar)
                  </span>
                </div>

                <div className="text-right">
                  <p className="text-[#404943] font-sora text-[11px] mb-2 font-medium">
                    {artisans.length} artisans recommandés
                  </p>
                  <div className="flex items-center justify-end -space-x-3">
                    {artisans.slice(0, 3).map((art, idx) => (
                      <div
                        key={art.id}
                        className="w-10 h-10 rounded-full border-2 border-white overflow-hidden shadow-sm"
                      >
                        <img src={art.avatarUrl} alt={art.name} className="w-full h-full object-cover" />
                      </div>
                    ))}
                    <div className="w-10 h-10 rounded-full border-2 border-white bg-[#f0eded] text-[#404943] flex items-center justify-center text-[10px] font-bold">
                      +{artisans.length - 3 > 0 ? artisans.length - 3 : 5}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-3 px-1">
            <p className="text-xs text-[#404943] font-sora flex items-start gap-1.5">
              <span className="material-symbols-outlined text-[16px] text-[#004129] shrink-0 mt-0.5">
                info
              </span>
              <span>{aiResult.explanation}</span>
            </p>
          </div>
        </section>
      </main>

      {/* Fixed Bottom Action */}
      <footer className="fixed bottom-0 left-0 right-0 p-4 bg-[#fcf9f8]/90 backdrop-blur-md border-t border-[#e5e2e1] z-50 pb-safe">
        <button
          onClick={() => {
            const matched = artisans.find((a) => a.id === 'idrissa-diop') || artisans[0];
            setSelectedArtisan(matched);
            setCurrentView('artisan_profile');
          }}
          className="w-full max-w-xl mx-auto py-4 rounded-full bg-[#E8A73B] text-white font-bold text-base md:text-lg shadow-lg active:scale-[0.98] transition-transform flex items-center justify-center gap-2 cursor-pointer hover:brightness-105"
        >
          <span>Voir les artisans</span>
          <span className="material-symbols-outlined">arrow_forward</span>
        </button>
      </footer>
    </div>
  );
};
