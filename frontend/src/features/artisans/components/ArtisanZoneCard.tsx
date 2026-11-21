import React from 'react';
import { MapPin, PenLine } from 'lucide-react';
import { ButtonLink } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { ErrorState } from '../../../components/ui/ErrorState';
import { SectionHeader } from '../../../components/ui/SectionHeader';
import { Skeleton } from '../../../components/ui/Skeleton';
import { useMyArtisanZone } from '../hooks/useMyArtisanZone';
import { formatRadiusKm, zoneChangesLabel, zonePlacementLabel } from '../zoneText';
import { ZONE_ANCHOR } from './ArtisanZoneSection';

/**
 * Carte « Ma zone d'intervention » du profil Pro : ce que le serveur a
 * retenu (source, quartier), le rayon de chaque métier, les changements
 * encore possibles, et un bouton Modifier vers l'étape de l'onboarding.
 */
export const ArtisanZoneCard: React.FC<{ enabled: boolean }> = ({ enabled }) => {
  const { data: zone, isLoading, error, reload } = useMyArtisanZone(enabled);

  return (
    <section aria-labelledby="ma-zone" className="space-y-3">
      <SectionHeader id="ma-zone" title="Ma zone d’intervention" />
      {isLoading && !zone ? (
        <Skeleton className="h-28 rounded-card" />
      ) : error && !zone ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : zone ? (
        <Card className="space-y-3">
          <p
            className={
              zone.placed
                ? 'flex items-center gap-2 font-semibold text-foreground'
                : 'flex items-center gap-2 font-semibold text-destructive'
            }
          >
            <MapPin aria-hidden className="w-4 h-4 shrink-0" />
            {zonePlacementLabel(zone)}
          </p>
          {zone.trades.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {zone.trades.map((trade) => (
                <li key={trade.id} className="flex justify-between gap-3">
                  <span className="text-foreground">{trade.tradeLabel}</span>
                  <span className="text-muted-foreground">
                    rayon {formatRadiusKm(trade.serviceRadiusM)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Aucun métier déclaré pour le moment.</p>
          )}
          <p className="text-sm text-muted-foreground">{zoneChangesLabel(zone)}</p>
          <ButtonLink
            to={`/pro/onboarding#${ZONE_ANCHOR}`}
            variant="outline"
            size="sm"
            leadingIcon={<PenLine aria-hidden className="w-4 h-4" />}
          >
            Modifier
          </ButtonLink>
        </Card>
      ) : null}
    </section>
  );
};
