import { describe, expect, it } from 'vitest';
import { api } from './index';
import { httpApiClient, notImplemented } from './http-impl';
import { ApiError } from './types';

describe('api (point d’entrée unique)', () => {
  it('is the HTTP client itself — no per-method fallback onto the mock', () => {
    expect(api).toBe(httpApiClient);
  });

  it('exposes only real implementations for every contract method', () => {
    for (const [name, method] of Object.entries(api)) {
      expect(typeof method, name).toBe('function');
    }
  });
});

describe('notImplemented', () => {
  it('fails explicitly with a dedicated code and a displayable message', () => {
    let caught: unknown;
    try {
      notImplemented('La messagerie');
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught).toMatchObject({
      code: 'not_implemented',
      message: "La messagerie n'est pas encore disponible. Merci de réessayer plus tard.",
    });
  });
});
