import React from 'react';
import { ChevronRight, MapPin } from 'lucide-react';
import { Link } from 'react-router';
import { Avatar } from '../../../components/ui/Avatar';
import { Rating } from '../../../components/ui/Rating';
import { Skeleton } from '../../../components/ui/Skeleton';
import { VerifiedBadge } from '../../../components/ui/VerifiedBadge';
import { cardClasses } from '../../../components/ui/styles';
import { cn } from '../../../lib/cn';
import type { Artisan } from '../../../types';

interface ArtisanCardProps {
  artisan: Artisan;
  /** Niveau de titre du nom, selon la hiérarchie de la page. */
  headingLevel?: 'h2' | 'h3';
}

/**
 * Carte artisan, identique sur l'accueil, la recherche et les résultats
 * de l'assistant IA. L'artisan est le héros : photo, nom en Fraunces,
 * badge Vérifié, note or, distance et prix indicatif lisibles d'un coup
 * d'œil. Toute la carte est un seul lien vers la fiche (une seule
 * tabulation, zone tactile maximale). Aucun numéro de téléphone, jamais.
 */
export const ArtisanCard: React.FC<ArtisanCardProps> = ({ artisan, headingLevel = 'h3' }) => {
  const Heading = headingLevel;
  return (
    <Link
      to={`/artisans/${artisan.id}`}
      className={cardClasses({ interactive: true, className: 'flex gap-4' })}
    >
      <Avatar name={artisan.name} src={artisan.avatarUrl} size="lg" shape="rounded" decorative />

      <div className="min-w-0 flex-1 flex flex-col gap-1">
        <div className="flex items-start justify-between gap-2">
          <Heading className="font-display text-title font-semibold text-foreground truncate">
            {artisan.name}
          </Heading>
          {artisan.verified && <VerifiedBadge size="sm" />}
        </div>

        <p className="text-sm text-muted-foreground truncate">
          {artisan.tags.length > 0 ? artisan.tags.join(' · ') : 'Artisan'}
        </p>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <Rating value={artisan.rating} count={artisan.reviewCount} />
          {artisan.distance && (
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <MapPin aria-hidden className="w-3.5 h-3.5" />
              <span className="sr-only">Distance :</span>
              {artisan.distance}
            </span>
          )}
          {!artisan.available && (
            <span className="text-xs font-semibold text-muted-foreground">Indisponible</span>
          )}
        </div>

        <div className="mt-auto pt-1 flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-primary">{artisan.priceBase}</span>
          <ChevronRight aria-hidden className="w-5 h-5 text-primary-emerald shrink-0" />
        </div>
      </div>
    </Link>
  );
};

/** Squelette à la forme exacte de la carte (aucun saut de mise en page au chargement). */
export const ArtisanCardSkeleton: React.FC<{ className?: string }> = ({ className }) => (
  <div className={cardClasses({ className: cn('flex gap-4', className) })}>
    <Skeleton className="w-18 h-18 rounded-2xl shrink-0" />
    <div className="flex-1 space-y-2 py-1">
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-3 w-1/3" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  </div>
);
