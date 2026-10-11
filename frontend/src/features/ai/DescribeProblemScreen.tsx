import React, { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Send, Sparkles, TriangleAlert } from 'lucide-react';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import { AppBar } from '../../components/ui/AppBar';
import { Avatar } from '../../components/ui/Avatar';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { ErrorState } from '../../components/ui/ErrorState';
import { TextAreaField } from '../../components/ui/Field';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill, type StatusTone } from '../../components/ui/StatusPill';
import { VerifiedBadge } from '../../components/ui/VerifiedBadge';
import { api, ApiError } from '../../lib/api';
import type { ArtisanFilters } from '../../lib/api/types';
import { getCurrentPosition, type Coordinates } from '../../lib/geo';
import type { AIAnalysisResult, ServiceRequest } from '../../types';
import { useAuth } from '../auth/hooks/useAuth';
import { ArtisanCard, ArtisanCardSkeleton } from '../artisans/components/ArtisanCard';
import { useArtisan } from '../artisans/hooks/useArtisan';
import { useArtisans } from '../artisans/hooks/useArtisans';
import { useAnalyzeProblem } from './hooks/useAnalyzeProblem';

/** Longueur maximale de la description (alignée sur le champ côté serveur). */
const MAX_LENGTH = 500;
/** En dessous, l'IA n'a pas assez de matière : on n'appelle pas l'endpoint. */
const MIN_ANALYSIS_LENGTH = 15;
/**
 * L'analyse part après une pause de frappe. L'ancien écran appelait l'IA à
 * CHAQUE caractère, sur un endpoint public limité en débit : la limite
 * s'épuisait en une phrase.
 */
const ANALYSIS_DEBOUNCE_MS = 800;
/** Artisans montrés sous le résultat. */
const SUGGESTED_COUNT = 3;

const URGENCY: Record<AIAnalysisResult['urgencyCode'], { label: string; tone: StatusTone }> = {
  normal: { label: 'Normale', tone: 'info' },
  urgent: { label: 'Urgente', tone: 'warning' },
  immediat: { label: 'Immédiate', tone: 'danger' },
};

function searchUrlFor(tradeCode: string, position: Coordinates): string {
  return `/recherche?trade=${encodeURIComponent(tradeCode)}&lat=${position.lat}&lng=${position.lng}`;
}

/**
 * Demande assistée par l'IA (/demande).
 *
 * 1. Le client décrit son problème ; l'analyse (métier, estimation,
 *    urgence) se met à jour après chaque pause de frappe.
 * 2. Le résultat ressort sur une carte vert profond, suivi de trois
 *    artisans du métier détecté.
 * 3. L'action crée la demande (POST /requests) puis :
 *    - si l'on vient d'une fiche artisan (`?artisan=<id>`) et que le métier
 *      détecté est le sien : la demande lui est adressée directement
 *      (POST /interventions) ;
 *    - sinon : recherche filtrée côté serveur sur le métier et la position.
 *
 * Aucune donnée simulée : ni description ni photo préremplies, ni faux
 * enregistrement vocal (il ajoutait un texte inventé à la vraie demande).
 */
export const DescribeProblemScreen: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const auth = useAuth();
  const {
    data: aiResult,
    isLoading: isAnalyzing,
    error: analysisError,
    analyze,
  } = useAnalyzeProblem();

  const targetArtisanId = searchParams.get('artisan');
  const { data: targetArtisan } = useArtisan(targetArtisanId);

  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Demande déjà créée mais non adressée à l'artisan visé (refus serveur) :
  // on ne la recrée jamais, on propose les autres artisans du métier.
  const [orphanRequest, setOrphanRequest] = useState<{
    request: ServiceRequest;
    position: Coordinates;
  } | null>(null);

  const trimmed = description.trim();
  const isDescriptionReady = trimmed.length >= MIN_ANALYSIS_LENGTH;

  useEffect(() => {
    if (trimmed.length < MIN_ANALYSIS_LENGTH) return;
    const timer = setTimeout(() => analyze(trimmed), ANALYSIS_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [trimmed, analyze]);

  // Trois artisans du métier détecté (aucun appel avant la première analyse).
  const detectedTrade = aiResult?.tradeCode ?? null;
  const suggestedFilters = useMemo<ArtisanFilters | undefined>(
    () => (detectedTrade ? { trade: detectedTrade, pageSize: SUGGESTED_COUNT } : undefined),
    [detectedTrade],
  );
  const {
    data: suggested,
    isLoading: isSuggestedLoading,
    error: suggestedError,
    reload: reloadSuggested,
  } = useArtisans(suggestedFilters, { enabled: detectedTrade !== null });

  // Relais depuis une fiche : seulement si l'artisan exerce le métier détecté.
  const sendsToTarget =
    targetArtisan != null &&
    aiResult != null &&
    targetArtisan.tradeCodes.includes(aiResult.tradeCode);
  const targetMismatch =
    targetArtisan != null &&
    aiResult != null &&
    !targetArtisan.tradeCodes.includes(aiResult.tradeCode);

  // Seul un client crée une demande (POST /requests, réservé côté serveur).
  const isWrongRole = auth.isAuthenticated && auth.role !== 'client';

  const handleSubmit = async () => {
    if (!aiResult) return;

    // La création d'une demande exige d'être connecté : renvoie vers la
    // connexion et revient sur ce parcours ensuite (OtpScreen lit `from`).
    if (!auth.isAuthenticated) {
      navigate('/connexion', { state: { from: location } });
      return;
    }

    setSubmitError(null);
    setIsSubmitting(true);
    try {
      const position = await getCurrentPosition();
      const request = await api.createServiceRequest({
        tradeCode: aiResult.tradeCode,
        description: trimmed,
        // L'envoi de photo n'existe pas encore côté serveur (BUILD_PLAN.md §6 Lot 11).
        photoUrl: null,
        location: position,
        urgency: aiResult.urgencyCode,
        aiEstimateMinFcfa: aiResult.priceMinFcfa,
        aiEstimateMaxFcfa: aiResult.priceMaxFcfa,
      });

      if (sendsToTarget && targetArtisan) {
        try {
          await api.createIntervention({
            serviceRequestId: request.id,
            artisanId: targetArtisan.id,
          });
          navigate('/mes-interventions', { replace: true });
        } catch (err) {
          // La demande existe : on le dit, et on propose les autres artisans.
          setOrphanRequest({ request, position });
          setSubmitError(
            `Votre demande est enregistrée, mais n'a pas pu être envoyée à ${targetArtisan.name} : ${
              err instanceof ApiError ? err.message : 'erreur inattendue.'
            }`,
          );
        }
        return;
      }

      // Liste réellement filtrée côté serveur sur le métier détecté par
      // l'IA et la position -- jamais un artisan choisi au hasard
      // (AUDIT_PHASE2.md §6).
      navigate(searchUrlFor(aiResult.tradeCode, position));
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const ctaLabel = orphanRequest
    ? 'Voir les autres artisans'
    : isSubmitting
      ? 'Création de la demande...'
      : sendsToTarget && targetArtisan
        ? `Envoyer à ${targetArtisan.name}`
        : 'Voir les artisans';

  return (
    <>
      <AppBar title="Décrivez votre problème" backTo="/accueil" />

      <main className="flex-1 w-full max-w-2xl mx-auto px-4 pt-4 pb-40 space-y-6">
        {targetArtisan && (
          <Card tone="tint" className="flex items-center gap-3">
            <Avatar name={targetArtisan.name} src={targetArtisan.avatarUrl} size="sm" decorative />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-muted-foreground">Demande destinée à</p>
              <p className="font-semibold text-foreground truncate">{targetArtisan.name}</p>
            </div>
            {targetArtisan.verified && <VerifiedBadge />}
          </Card>
        )}

        <TextAreaField
          label="Votre problème"
          value={description}
          onChange={(event) => setDescription(event.target.value.slice(0, MAX_LENGTH))}
          maxLength={MAX_LENGTH}
          rows={5}
          placeholder="Ex. : le robinet de la cuisine fuit sous l'évier depuis ce matin."
          hint={`${description.length} / ${MAX_LENGTH} — plus vous êtes précis, meilleure est l'estimation.`}
        />

        <section aria-labelledby="analyse-titre" aria-live="polite" className="space-y-4">
          <h2 id="analyse-titre" className="sr-only">
            Analyse de votre demande
          </h2>

          {!aiResult && isAnalyzing ? (
            <Card tone="dark" padding="lg" className="space-y-3" aria-busy="true">
              <p className="text-caption font-semibold uppercase tracking-[0.12em] text-accent">
                Analyse en cours…
              </p>
              <div className="space-y-2 [&>div]:bg-white/15">
                <Skeleton className="h-7 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-4 w-1/3" />
              </div>
            </Card>
          ) : !aiResult && analysisError ? (
            <ErrorState message={analysisError.message} onRetry={() => analyze(trimmed)} />
          ) : aiResult ? (
            <>
              {/* Le résultat ressort : carte vert profond, détails en or. */}
              <Card tone="dark" padding="lg" className="space-y-5">
                <div className="flex items-center justify-between gap-2">
                  <p className="inline-flex items-center gap-2 text-caption font-semibold uppercase tracking-[0.12em] text-accent">
                    <Sparkles aria-hidden className="w-4 h-4" />
                    Analyse IA
                  </p>
                  {isAnalyzing && (
                    <span className="text-xs text-primary-emerald-foreground">Mise à jour…</span>
                  )}
                </div>
                <div className="space-y-1">
                  <p className="text-sm text-primary-emerald-foreground">Métier détecté</p>
                  <p className="font-display text-display-md font-semibold">{aiResult.trade}</p>
                </div>
                <dl className="grid grid-cols-2 gap-4 border-t border-white/15 pt-4">
                  <div className="space-y-1">
                    <dt className="text-sm text-primary-emerald-foreground">Estimation</dt>
                    <dd className="font-semibold">{aiResult.priceEstimate}</dd>
                  </div>
                  <div className="space-y-1">
                    <dt className="text-sm text-primary-emerald-foreground">Urgence</dt>
                    <dd>
                      <StatusPill tone={URGENCY[aiResult.urgencyCode].tone}>
                        {URGENCY[aiResult.urgencyCode].label}
                      </StatusPill>
                    </dd>
                  </div>
                </dl>
                <p className="text-sm text-primary-emerald-foreground">{aiResult.explanation}</p>
                <p className="text-xs text-primary-emerald-foreground/90">
                  Estimation indicative basée sur des cas similaires à Dakar : le prix final est
                  fixé par le devis de l&apos;artisan.
                </p>
              </Card>

              {targetMismatch && targetArtisan && (
                <Card tone="tint" className="flex items-start gap-3 text-sm text-foreground">
                  <TriangleAlert aria-hidden className="w-5 h-5 text-accent-foreground shrink-0" />
                  <span>
                    {aiResult.trade} ne fait pas partie des métiers de {targetArtisan.name}. Votre
                    demande vous mènera aux artisans de ce métier.
                  </span>
                </Card>
              )}

              {!sendsToTarget && (
                <div className="space-y-3">
                  <SectionHeader as="h3" title="Artisans pour ce métier" />
                  {isSuggestedLoading && suggested === null ? (
                    [0, 1, 2].map((key) => <ArtisanCardSkeleton key={key} />)
                  ) : suggestedError && suggested === null ? (
                    <ErrorState message={suggestedError.message} onRetry={reloadSuggested} />
                  ) : suggested && suggested.length > 0 ? (
                    <ul className="space-y-3">
                      {suggested.slice(0, SUGGESTED_COUNT).map((artisan) => (
                        <li key={artisan.id}>
                          <ArtisanCard artisan={artisan} />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <Card tone="tint" className="text-sm text-foreground">
                      Aucun artisan vérifié n&apos;est encore disponible pour ce métier. Votre
                      demande reste enregistrée et visible dans « Mes demandes ».
                    </Card>
                  )}
                </div>
              )}
            </>
          ) : (
            <Card tone="tint" className="flex items-start gap-3">
              <Sparkles aria-hidden className="w-5 h-5 text-primary-emerald shrink-0 mt-0.5" />
              <p className="text-sm text-foreground">
                {isDescriptionReady
                  ? 'Analyse de votre description…'
                  : "Décrivez votre problème en quelques phrases : notre assistant identifie le métier, estime le budget et l'urgence."}
              </p>
            </Card>
          )}
        </section>
      </main>

      <div className="fixed bottom-0 inset-x-0 z-40 bg-surface/95 backdrop-blur-md shadow-bar px-4 pt-3 pb-safe">
        <div className="max-w-xl mx-auto space-y-2 pb-1">
          {submitError && (
            <p role="alert" className="text-sm text-destructive text-center">
              {submitError}
            </p>
          )}
          {isWrongRole && (
            <p className="text-xs text-center text-muted-foreground">
              La création d&apos;une demande est réservée aux comptes clients.
            </p>
          )}
          {orphanRequest ? (
            <ButtonLink
              to={searchUrlFor(orphanRequest.request.tradeCode, orphanRequest.position)}
              variant="primary"
              size="lg"
              fullWidth
              trailingIcon={<ArrowRight aria-hidden className="w-5 h-5" />}
            >
              {ctaLabel}
            </ButtonLink>
          ) : (
            <Button
              variant="primary"
              size="lg"
              fullWidth
              onClick={handleSubmit}
              isLoading={isSubmitting}
              disabled={!aiResult || !isDescriptionReady || isWrongRole}
              trailingIcon={
                sendsToTarget ? (
                  <Send aria-hidden className="w-5 h-5" />
                ) : (
                  <ArrowRight aria-hidden className="w-5 h-5" />
                )
              }
            >
              {ctaLabel}
            </Button>
          )}
        </div>
      </div>
    </>
  );
};
