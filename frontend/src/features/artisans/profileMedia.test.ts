import { describe, expect, it } from 'vitest';
import type { ProfileMediaConstraints } from '../../types';
import {
  acceptAttribute,
  constraintsHint,
  formatMegabytes,
  validateProfileMediaFile,
} from './profileMedia';

const constraints: ProfileMediaConstraints = {
  acceptedMimeTypes: ['image/jpeg', 'image/png'],
  maxPixels: 50_000_000,
  avatar: { maxUploadBytes: 2 * 1024 * 1024, maxSidePx: 512 },
  cover: { maxUploadBytes: 10 * 1024 * 1024, maxSidePx: 1600 },
};

function fileOf(size: number, type: string): File {
  return new File([new Uint8Array(size)], 'f', { type });
}

describe('profileMedia', () => {
  it('applies the per-kind limit announced by the server', () => {
    const threeMo = fileOf(3 * 1024 * 1024, 'image/jpeg');
    expect(validateProfileMediaFile(threeMo, 'avatar', constraints)).toBe(
      'La photo de profil dépasse la taille maximale autorisée (2 Mo).',
    );
    expect(validateProfileMediaFile(threeMo, 'cover', constraints)).toBeNull();
  });

  it('rejects a type the server does not accept, but tolerates an unknown browser type', () => {
    expect(validateProfileMediaFile(fileOf(10, 'image/gif'), 'cover', constraints)).toBe(
      'La photo de couverture doit être une image JPEG ou PNG.',
    );
    expect(validateProfileMediaFile(fileOf(10, ''), 'cover', constraints)).toBeNull();
  });

  it('never guesses a limit when the constraints are unknown', () => {
    expect(validateProfileMediaFile(fileOf(50 * 1024 * 1024, 'image/jpeg'), 'cover', null)).toBeNull();
    expect(validateProfileMediaFile(fileOf(0, 'image/jpeg'), 'cover', null)).toBe(
      'Le fichier sélectionné est vide.',
    );
    expect(acceptAttribute(null)).toBe('image/*');
    expect(constraintsHint(null)).toBeNull();
  });

  it('formats sizes in French', () => {
    expect(formatMegabytes(10 * 1024 * 1024)).toBe('10 Mo');
    expect(formatMegabytes(2.5 * 1024 * 1024)).toBe('2,5 Mo');
    expect(constraintsHint(constraints)).toBe('JPEG ou PNG, 10 Mo maximum');
  });
});
