import { describe, expect, it } from 'vitest';
import { formatDayLabel, formatShortTimestamp, isSameDay } from './datetime';

// Dates construites en heure locale : le test ne dépend pas du fuseau de la machine.
const now = new Date(2026, 9, 11, 15, 30);
const at = (day: number, hour = 9) => new Date(2026, 9, day, hour, 5).toISOString();

describe('formatShortTimestamp', () => {
  it("donne l'heure pour aujourd'hui, « Hier » pour la veille", () => {
    expect(formatShortTimestamp(at(11), now)).toMatch(/09:05/);
    expect(formatShortTimestamp(at(10), now)).toBe('Hier');
  });

  it('donne le jour de la semaine sur la dernière semaine, sinon la date', () => {
    expect(formatShortTimestamp(at(8), now)).toBe('jeudi');
    expect(formatShortTimestamp(at(1), now)).toMatch(/1 oct/);
  });
});

describe('formatDayLabel', () => {
  it('nomme les jours récents et date les autres', () => {
    expect(formatDayLabel(at(11), now)).toBe("Aujourd'hui");
    expect(formatDayLabel(at(10), now)).toBe('Hier');
    expect(formatDayLabel(at(2), now)).toBe('2 octobre 2026');
  });
});

describe('isSameDay', () => {
  it('compare des jours calendaires, pas des durées', () => {
    expect(isSameDay(at(11, 0), at(11, 23))).toBe(true);
    expect(isSameDay(at(10, 23), at(11, 0))).toBe(false);
  });
});
