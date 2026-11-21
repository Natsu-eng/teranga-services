import React from 'react';
import { MapPinOff } from 'lucide-react';
import { Link } from 'react-router';
import { useMyArtisanZone } from '../hooks/useMyArtisanZone';
import { ZONE_ANCHOR } from './ArtisanZoneSection';

/**
 * Bandeau du tableau de bord d'un artisan NON placé : il ne reçoit aucune
 * demande tant qu'il n'a pas choisi sa zone, et doit le savoir. Rien n'est
 * affiché tant que la zone n'est pas connue (jamais une alerte supposée).
 */
export const UnplacedBanner: React.FC<{ enabled: boolean }> = ({ enabled }) => {
  const { data: zone } = useMyArtisanZone(enabled);
  if (!zone || zone.placed) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-card bg-destructive-soft text-destructive p-4"
    >
      <MapPinOff aria-hidden className="w-5 h-5 shrink-0 mt-0.5" />
      <div className="space-y-1">
        <p className="font-semibold">
          Vous n’êtes placé nulle part : vous ne recevez aucune demande
        </p>
        <Link
          to={`/pro/onboarding#${ZONE_ANCHOR}`}
          className="text-sm font-semibold underline underline-offset-2"
        >
          Choisir ma zone d’intervention
        </Link>
      </div>
    </div>
  );
};
