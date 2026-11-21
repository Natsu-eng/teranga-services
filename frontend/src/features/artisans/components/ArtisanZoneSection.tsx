import React, { useEffect, useId, useState } from 'react';
import { LocateFixed, MapPin, PenLine } from 'lucide-react';
import { useLocation } from 'react-router';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { ErrorState } from '../../../components/ui/ErrorState';
import { SelectField, TextField } from '../../../components/ui/Field';
import { Skeleton } from '../../../components/ui/Skeleton';
import { ApiError, api } from '../../../lib/api';
import type { ArtisanLocationInput } from '../../../lib/api/types';
import { GeolocationError, getCurrentPosition } from '../../../lib/geo';
import { groupByDepartment } from '../../../lib/places';
import type { ArtisanZone, ZoneTrade } from '../../../types';
import { usePlace } from '../../location/usePlace';
import { formatRadiusKm, zoneChangesLabel, zonePlacementLabel } from '../zoneText';

/** Identifiant d'ancre : le bandeau « placé nulle part » y renvoie. */
export const ZONE_ANCHOR = 'zone';

type Mode = 'quartier' | 'gps';

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError || err instanceof GeolocationError) return err.message;
  return fallback;
}

const TradeRadiusRow: React.FC<{
  trade: ZoneTrade;
  radiusMaxM: number;
  onSaved: (zone: ArtisanZone) => void;
}> = ({ trade, radiusMaxM, onSaved }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [radiusKm, setRadiusKm] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const maxKm = radiusMaxM / 1000;
  const value = Number(radiusKm.replace(',', '.'));
  const isValid = radiusKm !== '' && value > 0 && value <= maxKm;

  const save = async () => {
    if (!isValid) return;
    setError(null);
    setIsSaving(true);
    try {
      onSaved(await api.updateArtisanTradeRadius(trade.id, Math.round(value * 1000)));
      setIsEditing(false);
    } catch (err) {
      setError(errorMessage(err, "Le rayon n'a pas pu être modifié. Réessayez."));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <li className="rounded-field bg-emerald-tint px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm">
          <span className="font-semibold text-foreground">{trade.tradeLabel}</span>
          <span className="text-muted-foreground">
            {' '}
            · rayon {formatRadiusKm(trade.serviceRadiusM)}
          </span>
        </p>
        {!isEditing && (
          <Button
            variant="ghost"
            size="sm"
            leadingIcon={<PenLine aria-hidden className="w-4 h-4" />}
            onClick={() => {
              setRadiusKm(String(trade.serviceRadiusM / 1000));
              setIsEditing(true);
            }}
          >
            Modifier le rayon
            <span className="sr-only"> de {trade.tradeLabel}</span>
          </Button>
        )}
      </div>
      {isEditing && (
        <div className="space-y-2">
          <TextField
            label={`Rayon pour ${trade.tradeLabel} (km)`}
            type="number"
            inputMode="decimal"
            min={0.1}
            max={maxKm}
            step={0.1}
            value={radiusKm}
            onChange={(event) => setRadiusKm(event.target.value)}
            hint={`${formatRadiusKm(radiusMaxM)} au plus.`}
          />
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <Button
              variant="brand"
              size="sm"
              isLoading={isSaving}
              disabled={!isValid}
              onClick={save}
            >
              Enregistrer
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setIsEditing(false)}>
              Annuler
            </Button>
          </div>
        </div>
      )}
    </li>
  );
};

interface ArtisanZoneSectionProps {
  zone: ArtisanZone | null;
  isLoading: boolean;
  error: ApiError | null;
  reload: () => void;
  onZoneChange: (zone: ArtisanZone) => void;
}

/**
 * Étape obligatoire « Ma zone d'intervention » : sans elle, l'artisan ne
 * reçoit aucune demande. Deux façons de se placer, le quartier EN PREMIER :
 * - « Choisir mon quartier » : le serveur pose le centre officiel de la
 *   commune ;
 * - « Utiliser ma position GPS » : demandée sur clic seulement, arrondie
 *   par le serveur avant d'être enregistrée.
 * Le libellé dit honnêtement ce qui a été retenu, jamais plus précis.
 */
export const ArtisanZoneSection: React.FC<ArtisanZoneSectionProps> = ({
  zone,
  isLoading,
  error,
  reload,
  onZoneChange,
}) => {
  const titleId = useId();
  const location = useLocation();
  const { catalog, catalogError, reloadCatalog } = usePlace();
  const [mode, setMode] = useState<Mode>('quartier');
  const [neighborhoodId, setNeighborhoodId] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Arrivée depuis le bandeau « placé nulle part » : l'étape est montrée.
  useEffect(() => {
    if (location.hash === `#${ZONE_ANCHOR}`) {
      document.getElementById(ZONE_ANCHOR)?.scrollIntoView?.();
    }
  }, [location.hash]);

  const place = async (getLocation: () => Promise<ArtisanLocationInput>) => {
    setSaveError(null);
    setIsSaving(true);
    try {
      const input = await getLocation();
      await api.updateMyArtisanProfile({ location: input });
      onZoneChange(await api.getMyArtisanZone());
    } catch (err) {
      setSaveError(
        `${errorMessage(err, "Votre zone n'a pas pu être enregistrée.")} Votre zone enregistrée n'a pas changé.`,
      );
    } finally {
      setIsSaving(false);
    }
  };

  const placeInNeighborhood = () => {
    if (!neighborhoodId) return;
    void place(async () => ({ source: 'neighborhood', neighborhoodId }));
  };
  const placeWithGps = () => {
    void place(async () => ({ source: 'gps', ...(await getCurrentPosition()) }));
  };

  return (
    <Card
      as="section"
      padding="lg"
      aria-labelledby={titleId}
      className="space-y-4 scroll-mt-24"
      id={ZONE_ANCHOR}
    >
      <h2
        id={titleId}
        className="font-display text-display-sm font-semibold text-primary flex items-center gap-2"
      >
        <MapPin aria-hidden className="w-5 h-5" /> Ma zone d&apos;intervention
      </h2>

      {isLoading && !zone ? (
        <Skeleton className="h-24 rounded-card" />
      ) : error && !zone ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : zone ? (
        <>
          <div role="status" className="space-y-1">
            <p
              className={
                zone.placed ? 'font-semibold text-foreground' : 'font-semibold text-destructive'
              }
            >
              {zonePlacementLabel(zone)}
            </p>
            <p className="text-sm text-muted-foreground">
              {zone.placed
                ? 'Vous recevez les demandes situées dans le rayon de chacun de vos métiers autour de ce point.'
                : 'Tant que vous n’êtes pas placé, vous ne recevez aucune demande.'}
            </p>
            <p className="text-sm text-muted-foreground">{zoneChangesLabel(zone)}</p>
          </div>

          <div className="flex flex-wrap gap-2" role="group" aria-label="Comment vous placer">
            <Button
              variant={mode === 'quartier' ? 'brand' : 'outline'}
              size="sm"
              aria-pressed={mode === 'quartier'}
              onClick={() => setMode('quartier')}
            >
              Choisir mon quartier
            </Button>
            <Button
              variant={mode === 'gps' ? 'brand' : 'outline'}
              size="sm"
              aria-pressed={mode === 'gps'}
              onClick={() => setMode('gps')}
            >
              Utiliser ma position GPS
            </Button>
          </div>

          {mode === 'quartier' ? (
            catalog ? (
              <div className="space-y-3">
                <SelectField
                  label="Mon quartier"
                  value={neighborhoodId}
                  onChange={(event) => setNeighborhoodId(event.target.value)}
                  hint="Vous serez placé au centre officiel de ce quartier."
                >
                  <option value="">Choisir un quartier</option>
                  {groupByDepartment(catalog.items).map((group) => (
                    <optgroup key={group.label} label={`Département de ${group.label}`}>
                      {group.items.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </SelectField>
                <Button
                  variant="primary"
                  fullWidth
                  isLoading={isSaving}
                  disabled={!neighborhoodId}
                  onClick={placeInNeighborhood}
                >
                  Me placer dans ce quartier
                </Button>
              </div>
            ) : catalogError ? (
              <ErrorState message={catalogError.message} onRetry={reloadCatalog} />
            ) : (
              <Skeleton className="h-12 rounded-field" />
            )
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Votre position est arrondie à environ {zone.gpsGridM} m avant d&apos;être
                enregistrée : votre adresse exacte n&apos;est jamais gardée ni montrée.
              </p>
              <Button
                variant="primary"
                fullWidth
                isLoading={isSaving}
                leadingIcon={<LocateFixed aria-hidden className="w-4 h-4" />}
                onClick={placeWithGps}
              >
                Me placer à ma position GPS
              </Button>
            </div>
          )}

          {saveError && (
            <p role="alert" className="text-sm text-destructive">
              {saveError}
            </p>
          )}

          {zone.trades.length > 0 && (
            <div className="space-y-2 pt-4 border-t border-border-faint">
              <h3 className="text-sm font-semibold text-foreground">Rayon par métier</h3>
              <ul className="space-y-2">
                {zone.trades.map((trade) => (
                  <TradeRadiusRow
                    key={trade.id}
                    trade={trade}
                    radiusMaxM={zone.radiusMaxM}
                    onSaved={onZoneChange}
                  />
                ))}
              </ul>
            </div>
          )}
        </>
      ) : null}
    </Card>
  );
};
