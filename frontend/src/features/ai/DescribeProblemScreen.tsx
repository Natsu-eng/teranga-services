import React, { useEffect, useState } from 'react';
import { ArrowLeft, X, Camera, Mic, Sparkles, Info, ArrowRight } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router';
import { SafeImage } from '../../components/ui/SafeImage';
import { Skeleton } from '../../components/ui/Skeleton';
import { ErrorState } from '../../components/ui/ErrorState';
import { api, ApiError } from '../../lib/api';
import { getCurrentPosition } from '../../lib/geo';
import { useAuth } from '../auth/hooks/useAuth';
import { useArtisans } from '../artisans/hooks/useArtisans';
import { useAnalyzeProblem } from './hooks/useAnalyzeProblem';

export const DescribeProblemScreen: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const { data: artisans, isLoading: isArtisansLoading, error: artisansError } = useArtisans();
  const { data: aiResult, isLoading: isAnalyzing, error: analysisError, analyze } = useAnalyzeProblem();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [description, setDescription] = useState<string>(
    "Le robinet de la cuisine fuit abondamment sous l'évier. L'eau s'écoule au niveau du joint du siphon depuis ce matin.",
  );
  const [photoPreview, setPhotoPreview] = useState<string | null>(
    '/images/describe-problem-photo-exemple.jpg',
  );
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [recordingTime, setRecordingTime] = useState<number>(0);

  // Analyze the pre-filled sample description once on mount; further edits
  // re-trigger analysis via the textarea's onChange handler below.
  useEffect(() => {
    analyze(description);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analyze]);

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
              (d) =>
                d +
                " [Note vocale 0:10]: 'J'ai aussi une forte odeur d'humidité sous le meuble de cuisine.'",
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

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col pb-32">
      {/* Top Bar */}
      <header className="sticky top-0 z-50 flex items-center h-16 px-4 bg-background/85 backdrop-blur-md border-b border-border">
        <button
          onClick={() => navigate(-1)}
          className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-surface-muted transition-colors active:scale-95 cursor-pointer"
        >
          <ArrowLeft className="text-foreground w-6 h-6" />
        </button>
        <h1 className="ml-3 font-bold text-lg md:text-xl text-primary">
          Décrivez votre problème
        </h1>
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
                  analyze(e.target.value);
                }
              }}
              maxLength={500}
              placeholder="Expliquez-nous ce qui ne va pas (ex: fuite d'eau, climatiseur qui ne refroidit plus)..."
              className="w-full h-40 p-4 rounded-2xl bg-white border border-border-strong focus:border-primary focus:ring-1 focus:ring-primary text-base text-foreground placeholder:text-muted-foreground-soft transition-all resize-none shadow-sm outline-none"
            />
            <div className="absolute bottom-3 right-3 text-xs text-muted-foreground-soft font-sora">
              {description.length} / 500
            </div>
          </div>

          {/* Photo Preview if attached */}
          {photoPreview && (
            <div className="relative w-full h-28 rounded-2xl overflow-hidden border border-border group">
              <SafeImage
                src={photoPreview}
                fallback="/images/placeholder-cover.svg"
                alt="Aperçu fuite"
                className="w-full h-full object-cover"
              />
              <button
                onClick={() => setPhotoPreview(null)}
                className="absolute top-2 right-2 bg-black/60 text-white rounded-full p-1 hover:bg-black transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
              <div className="absolute bottom-2 left-2 bg-black/50 backdrop-blur-sm text-white px-2.5 py-0.5 rounded-full text-xs font-sora">
                Photo jointe
              </div>
            </div>
          )}

          {/* Media Action Buttons */}
          <div className="flex gap-3">
            <label className="flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-full border-1.5 border-primary text-primary font-sora text-xs font-bold hover:bg-primary/5 active:scale-95 transition-all cursor-pointer">
              <Camera className="w-5 h-5" />
              <span>Ajouter une photo</span>
              <input type="file" accept="image/*" onChange={handlePhotoUpload} className="hidden" />
            </label>

            <button
              onClick={toggleRecording}
              className={`flex-1 flex items-center justify-center gap-2 py-3 px-4 rounded-full border-1.5 border-primary font-sora text-xs font-bold transition-all cursor-pointer ${
                isRecording
                  ? 'bg-destructive text-white border-destructive animate-pulse'
                  : 'text-primary hover:bg-primary/5 active:scale-95'
              }`}
            >
              <Mic className="w-5 h-5" />
              <span>{isRecording ? `Enregistrement 0:0${recordingTime}` : 'Message vocal'}</span>
            </button>
          </div>
        </section>

        {/* AI Analysis Result Card */}
        <section className="animate-in fade-in slide-in-from-bottom-4 duration-500">
          {!aiResult && isAnalyzing ? (
            <div className="bg-white rounded-2xl p-6 space-y-4">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-7 w-56" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : !aiResult && analysisError ? (
            <ErrorState message={analysisError.message} onRetry={() => analyze(description)} />
          ) : aiResult ? (
            <>
              <div className="magic-card-glow bg-white rounded-2xl p-6 relative overflow-hidden">
                {/* Ambient Shader Accent */}
                <div className="absolute -top-12 -right-12 w-32 h-32 bg-success opacity-20 rounded-full blur-2xl"></div>

                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Sparkles className="text-primary-emerald w-6 h-6" fill="currentColor" />
                    <h2 className="font-sora text-xs font-bold text-primary tracking-wider uppercase">
                      ANALYSE TERMINÉE
                    </h2>
                  </div>
                  {isAnalyzing && (
                    <span className="text-xs font-sora text-accent-foreground animate-pulse flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-accent-foreground animate-ping" />
                      Mise à jour IA...
                    </span>
                  )}
                </div>

                <div className="space-y-4">
                  <div>
                    <p className="text-muted-foreground font-sora text-[11px] font-bold uppercase mb-1">
                      Métier détecté
                    </p>
                    <p className="font-bold text-xl md:text-2xl text-primary-emerald">{aiResult.trade}</p>
                  </div>

                  <div className="flex justify-between items-end border-t border-border-faint pt-4">
                    <div>
                      <p className="text-muted-foreground font-sora text-[11px] font-bold uppercase mb-1">
                        Prix estimé
                      </p>
                      <p className="font-bold text-lg text-foreground">{aiResult.priceEstimate}</p>
                      <span className="text-[10px] text-muted-foreground-soft italic block mt-0.5">
                        (Estimation basée sur des cas similaires à Dakar)
                      </span>
                    </div>

                    <div className="text-right">
                      {isArtisansLoading && !artisans ? (
                        <div className="flex items-center justify-end -space-x-3">
                          {[0, 1, 2].map((key) => (
                            <Skeleton key={key} className="w-10 h-10 rounded-full border-2 border-white" />
                          ))}
                        </div>
                      ) : artisansError && !artisans ? (
                        <span className="text-xs font-sora text-muted-foreground-soft">
                          Artisans indisponibles
                        </span>
                      ) : (
                        artisans && (
                          <>
                            <p className="text-muted-foreground font-sora text-[11px] mb-2 font-medium">
                              {artisans.length} artisans recommandés
                            </p>
                            <div className="flex items-center justify-end -space-x-3">
                              {artisans.slice(0, 3).map((art) => (
                                <div
                                  key={art.id}
                                  className="w-10 h-10 rounded-full border-2 border-white overflow-hidden shadow-sm"
                                >
                                  <SafeImage
                                    src={art.avatarUrl}
                                    fallback="/images/placeholder-avatar.svg"
                                    alt={art.name}
                                    className="w-full h-full object-cover"
                                  />
                                </div>
                              ))}
                              <div className="w-10 h-10 rounded-full border-2 border-white bg-border-faint text-muted-foreground flex items-center justify-center text-[10px] font-bold">
                                +{artisans.length - 3 > 0 ? artisans.length - 3 : 5}
                              </div>
                            </div>
                          </>
                        )
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-3 px-1">
                <p className="text-xs text-muted-foreground font-sora flex items-start gap-1.5">
                  <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                  <span>{aiResult.explanation}</span>
                </p>
              </div>
            </>
          ) : null}
        </section>
      </main>

      {/* Fixed Bottom Action */}
      <footer className="fixed bottom-0 left-0 right-0 p-4 bg-background/90 backdrop-blur-md border-t border-border z-50 pb-safe">
        {submitError && (
          <p className="max-w-xl mx-auto mb-2 text-sm text-destructive text-center">{submitError}</p>
        )}
        <button
          onClick={async () => {
            if (!aiResult) return;

            // La création d'une demande exige d'être connecté : renvoie vers
            // la connexion et revient sur ce parcours ensuite (même
            // mécanisme que ProtectedRoute -- OtpScreen lit `state.from`).
            if (!auth.isAuthenticated) {
              navigate('/connexion', { state: { from: location } });
              return;
            }

            setSubmitError(null);
            setIsSubmitting(true);
            try {
              const position = await getCurrentPosition();
              await api.createServiceRequest({
                tradeCode: aiResult.tradeCode,
                description,
                // Upload photo réel hors périmètre (BUILD_PLAN.md §6 Lot 11) --
                // photoPreview n'est qu'un blob local, jamais envoyé.
                photoUrl: null,
                location: position,
                urgency: aiResult.urgencyCode,
                aiEstimateMinFcfa: aiResult.priceMinFcfa,
                aiEstimateMaxFcfa: aiResult.priceMaxFcfa,
              });
              // Liste réellement filtrée côté serveur sur le métier détecté
              // par l'IA et la position -- pas un artisan choisi au hasard
              // (AUDIT_PHASE2.md §6).
              navigate(
                `/recherche?trade=${encodeURIComponent(aiResult.tradeCode)}&lat=${position.lat}&lng=${position.lng}`,
              );
            } catch (err) {
              setSubmitError(
                err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
              );
            } finally {
              setIsSubmitting(false);
            }
          }}
          disabled={!aiResult || isSubmitting}
          className="w-full max-w-xl mx-auto py-4 rounded-full bg-accent text-white font-bold text-base md:text-lg shadow-lg active:scale-[0.98] transition-transform flex items-center justify-center gap-2 cursor-pointer hover:brightness-105 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <span>{isSubmitting ? 'Création de la demande...' : 'Voir les artisans'}</span>
          <ArrowRight className="w-6 h-6" />
        </button>
      </footer>
    </div>
  );
};
