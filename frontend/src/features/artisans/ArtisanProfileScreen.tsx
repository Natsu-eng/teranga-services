import React, { useState } from 'react';
import {
  Award,
  Camera,
  Clock,
  MapPin,
  MessageCircle,
  Pencil,
  ReceiptText,
  Share2,
  Star,
} from 'lucide-react';
import { useLocation, useNavigate, useParams } from 'react-router';
import { AppBar } from '../../components/ui/AppBar';
import { Avatar } from '../../components/ui/Avatar';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { ErrorState } from '../../components/ui/ErrorState';
import { IconButton } from '../../components/ui/IconButton';
import { Rating, StarRow } from '../../components/ui/Rating';
import { SafeImage } from '../../components/ui/SafeImage';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatTile } from '../../components/ui/StatTile';
import { StatusPill } from '../../components/ui/StatusPill';
import { VerifiedBadge } from '../../components/ui/VerifiedBadge';
import { useAuth } from '../auth/hooks/useAuth';
import { QuoteRequestSheet } from './components/QuoteRequestSheet';
import { useArtisan } from './hooks/useArtisan';

/** Nombre d'avis visibles avant « Voir tous les avis ». */
const REVIEWS_PREVIEW_COUNT = 3;

/**
 * Fiche publique d'un artisan (/artisans/:id).
 *
 * Le badge Vérifié s'affiche ici EN GRAND : c'est le signal de confiance
 * central. AUCUN numéro de téléphone n'est jamais affiché (protection
 * anti-désintermédiation) : le contact passe par « Message » et
 * « Demander un devis », dans l'application.
 *
 * Les actions dépendent du compte : un client demande un devis ; un
 * visiteur est d'abord invité à se connecter ; un artisan voit seulement
 * l'accès à l'édition de SA propre fiche (jamais de demande de devis).
 */
export const ArtisanProfileScreen: React.FC = () => {
  const { artisanId = '' } = useParams<{ artisanId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const { data: artisan, isLoading, error, reload } = useArtisan(artisanId);
  const [isQuoteOpen, setIsQuoteOpen] = useState(false);
  const [showAllReviews, setShowAllReviews] = useState(false);
  const [shareMessage, setShareMessage] = useState<string | null>(null);

  const isOwnProfile = auth.role === 'artisan' && auth.user?.artisanProfileId === artisanId;
  // Seul un client (ou un visiteur, invité à se connecter) sollicite un artisan.
  const canRequestQuote = auth.role === null || auth.role === 'client';

  const handleShare = async () => {
    const url = `${window.location.origin}/artisans/${artisanId}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: artisan?.name, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setShareMessage('Lien du profil copié.');
    } catch {
      // Partage annulé par l'utilisateur, ou presse-papiers refusé : on le dit.
      setShareMessage("Le lien n'a pas pu être copié.");
    }
    window.setTimeout(() => setShareMessage(null), 2500);
  };

  const handleRequestQuote = () => {
    if (!auth.isAuthenticated) {
      // Connexion d'abord, puis retour sur cette fiche (ProtectedRoute / OtpScreen lisent `from`).
      navigate('/connexion', { state: { from: location } });
      return;
    }
    setIsQuoteOpen(true);
  };

  const reviews = artisan?.reviews ?? [];
  const visibleReviews = showAllReviews ? reviews : reviews.slice(0, REVIEWS_PREVIEW_COUNT);

  return (
    <>
      <AppBar
        title="Profil artisan"
        backTo="/accueil"
        actions={
          artisan && (
            <IconButton label="Partager le profil" onClick={handleShare}>
              <Share2 aria-hidden className="w-5 h-5" />
            </IconButton>
          )
        }
      />

      {/* Annonce discrète du résultat du partage (lue par les lecteurs d'écran). */}
      <div role="status" aria-live="polite" className="sr-only">
        {shareMessage}
      </div>
      {shareMessage && (
        <div
          aria-hidden
          className="fixed top-20 left-1/2 -translate-x-1/2 z-50 rounded-full bg-primary px-4 py-2 text-sm text-white shadow-card-hover"
        >
          {shareMessage}
        </div>
      )}

      {isLoading && !artisan ? (
        <main className="w-full max-w-3xl mx-auto px-4 pt-4 space-y-5" aria-busy="true">
          <Skeleton className="w-full h-44 rounded-card" />
          <div className="space-y-2">
            <Skeleton className="h-7 w-1/2" />
            <Skeleton className="h-4 w-1/3" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Skeleton className="h-24 rounded-card" />
            <Skeleton className="h-24 rounded-card" />
          </div>
        </main>
      ) : error && !artisan ? (
        <main className="w-full max-w-3xl mx-auto px-4 pt-6 space-y-4">
          <ErrorState message={error.message} onRetry={reload} />
          <ButtonLink to="/accueil" variant="ghost" fullWidth>
            Retour à l&apos;accueil
          </ButtonLink>
        </main>
      ) : artisan ? (
        <main className="w-full pb-32">
          <section className="relative max-w-3xl mx-auto">
            <div className="h-44 md:h-64 overflow-hidden md:rounded-b-sheet bg-surface-muted">
              <SafeImage
                src={artisan.coverUrl}
                fallback="/images/placeholder-cover.svg"
                alt=""
                className="w-full h-full object-cover"
              />
            </div>
            <div className="absolute -bottom-12 left-4 md:left-6 rounded-full ring-4 ring-background">
              <Avatar name={artisan.name} src={artisan.avatarUrl} size="xl" />
            </div>
          </section>

          <div className="max-w-3xl mx-auto px-4 md:px-6 pt-16 space-y-7">
            <section aria-labelledby="artisan-nom" className="space-y-3">
              <div className="space-y-2">
                <h2
                  id="artisan-nom"
                  className="font-display text-display-md font-semibold text-primary"
                >
                  {artisan.name}
                </h2>
                {artisan.verified ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <VerifiedBadge size="lg" />
                    <span className="text-sm text-muted-foreground">
                      Identité et documents contrôlés par Téranga
                    </span>
                  </div>
                ) : (
                  <StatusPill tone="neutral">Vérification en cours</StatusPill>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                <Rating value={artisan.rating} count={artisan.reviewCount} size="md" />
                <span className="inline-flex items-center gap-1 text-muted-foreground">
                  <MapPin aria-hidden className="w-4 h-4" />
                  {artisan.location}
                  {artisan.distance && ` · ${artisan.distance}`}
                </span>
                <StatusPill tone={artisan.available ? 'success' : 'neutral'}>
                  {artisan.available ? 'Disponible' : 'Indisponible'}
                </StatusPill>
              </div>

              {artisan.tags.length > 0 && (
                <ul aria-label="Métiers" className="flex flex-wrap gap-2">
                  {artisan.tags.map((tag) => (
                    <li
                      key={tag}
                      className="rounded-full bg-emerald-tint px-3 py-1 text-sm font-medium text-primary"
                    >
                      {tag}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section aria-label="En chiffres" className="grid grid-cols-2 gap-3">
              <StatTile
                icon={<Star className="w-5 h-5" />}
                label="Avis clients"
                value={artisan.reviewCount}
              />
              <StatTile
                icon={<Award className="w-5 h-5" />}
                label="Expérience"
                value={artisan.stats.experience}
              />
              <StatTile
                icon={<ReceiptText className="w-5 h-5" />}
                label="Tarif indicatif"
                value={artisan.priceBase}
                className="col-span-2"
              />
            </section>

            <section aria-labelledby="a-propos" className="space-y-3">
              <SectionHeader id="a-propos" title="À propos" />
              <Card>
                <p className="text-base text-muted-foreground leading-relaxed whitespace-pre-line">
                  {artisan.bio || "Cet artisan n'a pas encore rédigé de présentation."}
                </p>
              </Card>
            </section>

            <section aria-labelledby="realisations" className="space-y-3">
              <SectionHeader id="realisations" title="Réalisations" />
              {artisan.realisations.length === 0 ? (
                <Card tone="tint" className="flex items-center gap-3 text-sm text-foreground">
                  <Camera aria-hidden className="w-5 h-5 text-primary-emerald shrink-0" />
                  Aucune réalisation publiée pour le moment.
                </Card>
              ) : (
                <ul className="-mx-4 px-4 flex gap-3 overflow-x-auto hide-scrollbar pb-2">
                  {artisan.realisations.map((realisation) => (
                    <li
                      key={realisation.id}
                      className="relative shrink-0 w-64 h-44 rounded-card overflow-hidden shadow-card"
                    >
                      <SafeImage
                        src={realisation.imageUrl}
                        fallback="/images/placeholder-cover.svg"
                        alt={realisation.altText}
                        className="w-full h-full object-cover"
                      />
                      <p className="absolute inset-x-0 bottom-0 bg-linear-to-t from-foreground/70 to-transparent p-3 text-sm font-semibold text-white">
                        {realisation.title}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section aria-labelledby="avis" className="space-y-3">
              <SectionHeader id="avis" title="Avis clients" />
              {reviews.length === 0 ? (
                <Card tone="tint" className="text-sm text-foreground">
                  Aucun avis pour le moment. Seul un client dont l&apos;intervention est terminée
                  peut en déposer un.
                </Card>
              ) : (
                <>
                  <ul className="space-y-3">
                    {visibleReviews.map((review) => (
                      <li key={review.id}>
                        <Card as="article" className="space-y-2">
                          <div className="flex items-center gap-3">
                            <Avatar name={review.author} size="sm" decorative />
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-semibold text-foreground truncate">
                                {review.author}
                              </p>
                              <StarRow value={review.rating} />
                            </div>
                            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground shrink-0">
                              <Clock aria-hidden className="w-3.5 h-3.5" />
                              {review.date}
                            </span>
                          </div>
                          <p className="text-sm text-muted-foreground leading-relaxed">
                            {review.comment}
                          </p>
                        </Card>
                      </li>
                    ))}
                  </ul>
                  {reviews.length > REVIEWS_PREVIEW_COUNT && (
                    <Button
                      variant="outline"
                      fullWidth
                      aria-expanded={showAllReviews}
                      onClick={() => setShowAllReviews((value) => !value)}
                    >
                      {showAllReviews ? 'Afficher moins d’avis' : `Voir les ${reviews.length} avis`}
                    </Button>
                  )}
                </>
              )}
            </section>
          </div>
        </main>
      ) : null}

      {artisan && (isOwnProfile || canRequestQuote) && (
        <div className="fixed bottom-0 inset-x-0 z-40 bg-surface/95 backdrop-blur-md shadow-bar px-4 pt-3 pb-safe">
          <div className="max-w-xl mx-auto flex gap-3 pb-1">
            {isOwnProfile ? (
              <ButtonLink
                to="/pro/onboarding"
                variant="brand"
                size="lg"
                fullWidth
                leadingIcon={<Pencil aria-hidden className="w-5 h-5" />}
              >
                Modifier ma fiche
              </ButtonLink>
            ) : (
              <>
                <ButtonLink
                  to={`/messages/${artisanId}`}
                  variant="outline"
                  size="md"
                  leadingIcon={<MessageCircle aria-hidden className="w-5 h-5" />}
                >
                  Message
                </ButtonLink>
                {/* Taille md et sans icône : les deux libellés tiennent sur une
                    ligne dès 360 px de large (vérifié en capture). */}
                <Button
                  variant="primary"
                  size="md"
                  className="flex-1"
                  disabled={!artisan.verified}
                  onClick={handleRequestQuote}
                >
                  Demander un devis
                </Button>
              </>
            )}
          </div>
          {!isOwnProfile && !artisan.verified && (
            <p className="max-w-xl mx-auto pb-1 text-xs text-center text-muted-foreground">
              Cet artisan n&apos;est pas encore vérifié : il ne peut pas recevoir de demande.
            </p>
          )}
        </div>
      )}

      {artisan && auth.role === 'client' && (
        <QuoteRequestSheet
          artisan={artisan}
          open={isQuoteOpen}
          onClose={() => setIsQuoteOpen(false)}
        />
      )}
    </>
  );
};
