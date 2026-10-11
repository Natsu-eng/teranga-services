import React, { useId, useState } from 'react';
import { LocateFixed, MapPin, TriangleAlert } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { SelectField } from '../../components/ui/Field';
import { GeolocationError, getCurrentPosition } from '../../lib/geo';
import {
  NEIGHBORHOODS,
  distanceFromDakarKm,
  isInServiceRegion,
  neighborhoodPlace,
  positionPlace,
  type Coordinates,
  type Place,
} from '../../lib/places';

/** Valeur de la liste pour « Ma position actuelle » (jamais un identifiant de quartier). */
const POSITION_OPTION = '__position';

function formatCoordinates({ lat, lng }: Coordinates): string {
  return `${lat.toFixed(4).replace('.', ',')} ; ${lng.toFixed(4).replace('.', ',')}`;
}

interface PlaceSectionProps {
  place: Place;
  onChange: (place: Place) => void;
}

/**
 * Lieu de l'intervention, choisi et VU par le client avant l'envoi.
 *
 * - Moyen principal : un quartier de Dakar (même liste que l'en-tête, avec
 *   ses vraies coordonnées).
 * - Le GPS n'est qu'une SUGGESTION : demandé seulement sur clic (le
 *   navigateur demande alors l'autorisation), son résultat est montré
 *   (coordonnées, distance à Dakar) et ne remplace le lieu qu'après
 *   confirmation. Un échec est dit, jamais remplacé en silence.
 */
export const PlaceSection: React.FC<PlaceSectionProps> = ({ place, onChange }) => {
  const titleId = useId();
  const [isLocating, setIsLocating] = useState(false);
  const [proposal, setProposal] = useState<Coordinates | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);

  const locate = async () => {
    setGeoError(null);
    setProposal(null);
    setIsLocating(true);
    try {
      setProposal(await getCurrentPosition());
    } catch (err) {
      setGeoError(
        err instanceof GeolocationError
          ? err.message
          : "Votre position n'a pas pu être déterminée.",
      );
    } finally {
      setIsLocating(false);
    }
  };

  const proposalDistance = proposal ? distanceFromDakarKm(proposal) : null;
  const proposalInRegion = proposal ? isInServiceRegion(proposal) : true;

  return (
    <section aria-labelledby={titleId} className="space-y-3">
      <h2 id={titleId} className="font-semibold text-foreground">
        Lieu de l&apos;intervention
      </h2>
      <SelectField
        label="Quartier"
        value={place.kind === 'quartier' ? place.neighborhoodId : POSITION_OPTION}
        onChange={(event) => {
          const value = event.target.value;
          if (value !== POSITION_OPTION) onChange(neighborhoodPlace(value));
        }}
        hint="L'artisan chiffre et se déplace d'après ce lieu."
      >
        {place.kind === 'position' && (
          <option value={POSITION_OPTION}>{place.label} (position GPS)</option>
        )}
        {NEIGHBORHOODS.map((neighborhood) => (
          <option key={neighborhood.id} value={neighborhood.id}>
            {neighborhood.label}
          </option>
        ))}
      </SelectField>

      {!proposal && (
        <Button
          variant="ghost"
          size="sm"
          onClick={locate}
          isLoading={isLocating}
          leadingIcon={<LocateFixed aria-hidden className="w-4 h-4" />}
        >
          {isLocating ? 'Recherche de votre position…' : 'Utiliser ma position actuelle'}
        </Button>
      )}

      {geoError && (
        <p role="alert" className="text-sm text-destructive">
          {geoError} Choisissez votre quartier dans la liste.
        </p>
      )}

      {proposal && (
        <Card tone="tint" padding="sm" className="space-y-3 text-sm" role="status">
          <p className="flex items-start gap-2 text-foreground">
            <MapPin aria-hidden className="w-4 h-4 shrink-0 mt-0.5 text-primary-emerald" />
            <span>
              Position trouvée : {formatCoordinates(proposal)}, à {proposalDistance} km du centre de
              Dakar.
            </span>
          </p>
          {!proposalInRegion && (
            <p className="flex items-start gap-2 text-destructive">
              <TriangleAlert aria-hidden className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Cette position est hors de la région de Dakar, où interviennent les artisans de
                Téranga. Choisissez plutôt le quartier des travaux.
              </span>
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant={proposalInRegion ? 'brand' : 'outline'}
              size="sm"
              onClick={() => {
                onChange(positionPlace(proposal));
                setProposal(null);
              }}
            >
              Utiliser cette position
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setProposal(null)}>
              Garder {place.label}
            </Button>
          </div>
        </Card>
      )}
    </section>
  );
};
