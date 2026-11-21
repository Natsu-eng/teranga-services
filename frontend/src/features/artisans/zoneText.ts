import type { ArtisanZone } from '../../types';

/** Libellé HONNÊTE de ce que le serveur a retenu (jamais plus précis). */
export function zonePlacementLabel(zone: ArtisanZone): string {
  if (!zone.placed) return 'Vous n’êtes placé nulle part';
  if (zone.source === 'neighborhood' && zone.neighborhood) {
    return `Placé au centre de ${zone.neighborhood.label}`;
  }
  return 'Placé à votre position GPS (précision réduite)';
}

export function formatRadiusKm(radiusM: number): string {
  const km = radiusM / 1000;
  return `${Number.isInteger(km) ? km : km.toFixed(1).replace('.', ',')} km`;
}

/** Changements restants, ou quand le prochain redevient possible. */
export function zoneChangesLabel(zone: ArtisanZone): string {
  if (zone.nextChangeAt) {
    const date = new Date(zone.nextChangeAt);
    const when = date.toLocaleString('fr-FR', {
      day: 'numeric',
      month: 'long',
      hour: '2-digit',
      minute: '2-digit',
    });
    return `Limite de changements atteinte : prochain changement possible le ${when}.`;
  }
  if (!zone.placed) return 'Votre premier placement ne compte pas dans les changements.';
  return `Changements encore possibles : ${zone.changesRemainingShort} sur ${zone.shortWindowHours} h, ${zone.changesRemainingLong} sur ${zone.longWindowDays} jours.`;
}
