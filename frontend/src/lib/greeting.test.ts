import { describe, expect, it } from 'vitest';
import { greetingFor, greetingLine } from './greeting';

function at(hour: number, minute = 0): Date {
  return new Date(2026, 9, 12, hour, minute);
}

describe('greeting', () => {
  it.each([
    [5, 0, 'Bonjour'], // début de matinée
    [9, 30, 'Bonjour'],
    [13, 0, 'Bonjour'], // après-midi
    [17, 59, 'Bonjour'],
    [18, 0, 'Bonsoir'], // soir
    [22, 15, 'Bonsoir'],
    [0, 30, 'Bonsoir'], // nuit
    [4, 59, 'Bonsoir'],
  ] as const)('à %sh%s : « %s »', (hour, minute, expected) => {
    expect(greetingFor(at(hour, minute))).toBe(expected);
  });

  it('salue par le prénom, ou seulement par la salutation', () => {
    expect(greetingLine('Dian', at(20))).toBe('Bonsoir, Dian');
    expect(greetingLine('Awa', at(10))).toBe('Bonjour, Awa');
    expect(greetingLine(null, at(20))).toBe('Bonsoir');
  });
});
