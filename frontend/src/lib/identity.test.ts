import { describe, expect, it } from 'vitest';
import { firstNameOf, hasRealName, looksLikePhoneNumber } from './identity';

describe('looksLikePhoneNumber', () => {
  it.each([
    '+221777278808',
    '777278808',
    '+221 77 727 88 08',
    '77-727-88-08',
    '(+221) 777.278.808',
  ])('reconnaît un numéro : %s', (value) => {
    expect(looksLikePhoneNumber(value)).toBe(true);
  });

  it.each(['Awa Diop', 'Idrissa', 'Ndèye Fatou Sarr', 'Jean-Paul 2', '', '12', 'A1234567'])(
    'ne confond jamais un nom (ou une valeur courte) avec un numéro : %s',
    (value) => {
      expect(looksLikePhoneNumber(value)).toBe(false);
    },
  );
});

describe('hasRealName', () => {
  it('refuse un nom vide, absent ou resté au numéro de téléphone', () => {
    expect(hasRealName('')).toBe(false);
    expect(hasRealName('   ')).toBe(false);
    expect(hasRealName(null)).toBe(false);
    expect(hasRealName(undefined)).toBe(false);
    expect(hasRealName('+221777278808')).toBe(false);
  });

  it('accepte un vrai nom', () => {
    expect(hasRealName('Awa Diop')).toBe(true);
  });
});

describe('firstNameOf', () => {
  it('renvoie le prénom d’un vrai nom', () => {
    expect(firstNameOf('  Awa   Diop ')).toBe('Awa');
  });

  it('ne renvoie jamais un numéro de téléphone comme prénom', () => {
    expect(firstNameOf('+221777278808')).toBeNull();
    expect(firstNameOf('')).toBeNull();
  });
});
