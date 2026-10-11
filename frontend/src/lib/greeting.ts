/**
 * Salutation selon l'heure locale de l'appareil : « Bonjour » le matin et
 * l'après-midi, « Bonsoir » le soir et la nuit — l'usage au Sénégal comme
 * en France.
 */

export type Greeting = 'Bonjour' | 'Bonsoir';

/** À partir de 18 h, on dit « Bonsoir » (fin de l'après-midi). */
export const EVENING_START_HOUR = 18;
/** Jusqu'à 5 h, il fait encore nuit : « Bonsoir » aussi. */
export const MORNING_START_HOUR = 5;

export function greetingFor(date: Date = new Date()): Greeting {
  const hour = date.getHours();
  return hour >= EVENING_START_HOUR || hour < MORNING_START_HOUR ? 'Bonsoir' : 'Bonjour';
}

/** « Bonsoir, Dian » — ou la salutation seule, sans vrai prénom. */
export function greetingLine(firstName: string | null, date: Date = new Date()): string {
  const greeting = greetingFor(date);
  return firstName ? `${greeting}, ${firstName}` : greeting;
}
