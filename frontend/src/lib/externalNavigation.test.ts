import { describe, expect, it } from 'vitest';
import { isSafeExternalUrl, navigateToExternal } from './externalNavigation';

describe('externalNavigation', () => {
  it('accepte une page de paiement http(s) absolue', () => {
    expect(isSafeExternalUrl('https://paiement.exemple/checkout/abc')).toBe(true);
    expect(isSafeExternalUrl('http://localhost:8000/api/v1/sandbox/checkout/abc')).toBe(true);
  });

  it('refuse tout autre schéma, même renvoyé par le serveur', () => {
    for (const url of ['javascript:alert(1)', 'data:text/html,x', '/relative', 'pas une url', '']) {
      expect(isSafeExternalUrl(url)).toBe(false);
      expect(() => navigateToExternal(url)).toThrow();
    }
  });
});
