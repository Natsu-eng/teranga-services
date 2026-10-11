/**
 * Formats de date de la messagerie (fuseau et langue de l'appareil, en
 * français). `now` est injectable pour des tests déterministes.
 */

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** Heure d'un message dans le fil : « 14:05 ». */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Horodatage compact d'une ligne de la liste : l'heure aujourd'hui,
 * « Hier », le jour de la semaine sur les 7 derniers jours, sinon la date.
 */
export function formatShortTimestamp(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
  if (days <= 0) return formatTime(iso);
  if (days === 1) return 'Hier';
  if (days < 7) return date.toLocaleDateString('fr-FR', { weekday: 'long' });
  return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}

/** Séparateur de jour dans le fil : « Aujourd'hui », « Hier », « 12 octobre 2026 ». */
export function formatDayLabel(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
  if (days <= 0) return "Aujourd'hui";
  if (days === 1) return 'Hier';
  return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
}

/** Vrai si les deux horodatages tombent le même jour (fuseau de l'appareil). */
export function isSameDay(a: string, b: string): boolean {
  return startOfDay(new Date(a)) === startOfDay(new Date(b));
}
