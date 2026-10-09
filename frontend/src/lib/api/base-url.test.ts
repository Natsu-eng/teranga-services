import { describe, expect, it } from 'vitest';
import { DEFAULT_API_BASE_URL, resolveApiBaseUrl } from './base-url';

describe('resolveApiBaseUrl', () => {
  it('falls back to the same-origin /api/v1 when unset or blank', () => {
    expect(resolveApiBaseUrl(undefined)).toBe(DEFAULT_API_BASE_URL);
    expect(resolveApiBaseUrl('   ')).toBe(DEFAULT_API_BASE_URL);
  });

  it('accepts an absolute https URL and strips trailing slashes', () => {
    expect(resolveApiBaseUrl('https://api.teranga.example/api/v1/')).toBe(
      'https://api.teranga.example/api/v1',
    );
  });

  it('accepts a same-origin relative path', () => {
    expect(resolveApiBaseUrl('/backend/api/v1/')).toBe('/backend/api/v1');
  });

  it.each([
    'api.teranga.example/api/v1',
    '//evil.example/api/v1',
    'javascript:alert(1)',
    'ftp://api.teranga.example/api/v1',
    'https://user:pass@api.teranga.example/api/v1',
    'https://api.teranga.example/api/v1?token=x',
  ])('rejects %s with an explicit error', (value) => {
    expect(() => resolveApiBaseUrl(value)).toThrow(/VITE_API_BASE_URL/);
  });
});
