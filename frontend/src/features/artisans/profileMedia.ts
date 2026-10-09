// Pré-contrôle des photos du profil artisan (avatar, couverture) AVANT envoi,
// d'après les contraintes que le backend applique réellement
// (`GET /artisans/me/media-constraints`) -- aucun plafond recopié en dur ici :
// modifier AVATAR_/COVER_MAX_UPLOAD_BYTES côté serveur suffit.
//
// Simple confort : il évite d'envoyer un gros fichier sur une connexion
// mobile lente pour se faire refuser ensuite, et ne consomme pas le budget
// d'envois partagé pour un fichier voué à l'échec. Le serveur reste la seule
// vraie barrière (décodage complet, magic bytes, dimensions) : si les
// contraintes n'ont pas pu être chargées, on laisse simplement le serveur
// trancher plutôt que de deviner.

import type { ProfileMediaConstraints } from '../../types';

export type ProfileMediaKind = 'avatar' | 'cover';

const LABEL: Record<ProfileMediaKind, string> = {
  avatar: 'La photo de profil',
  cover: 'La photo de couverture',
};

const FORMAT_NAME: Record<string, string> = {
  'image/jpeg': 'JPEG',
  'image/png': 'PNG',
};

function formatList(mimeTypes: string[]): string {
  const names = mimeTypes.map((type) => FORMAT_NAME[type] ?? type);
  return names.length <= 1 ? names.join('') : `${names.slice(0, -1).join(', ')} ou ${names.at(-1)}`;
}

/** Taille en Mo lisible (« 10 Mo », « 2,5 Mo »). */
export function formatMegabytes(bytes: number): string {
  const mo = bytes / (1024 * 1024);
  return `${Number.isInteger(mo) ? mo : mo.toFixed(1).replace('.', ',')} Mo`;
}

/** Valeur de l'attribut `accept` du sélecteur de fichier. */
export function acceptAttribute(constraints: ProfileMediaConstraints | null): string {
  return constraints ? constraints.acceptedMimeTypes.join(',') : 'image/*';
}

/** Aide affichée sous les boutons d'envoi (« JPEG ou PNG, 10 Mo maximum »). */
export function constraintsHint(constraints: ProfileMediaConstraints | null): string | null {
  if (!constraints) return null;
  const maxBytes = Math.max(constraints.avatar.maxUploadBytes, constraints.cover.maxUploadBytes);
  return `${formatList(constraints.acceptedMimeTypes)}, ${formatMegabytes(maxBytes)} maximum`;
}

/** Message d'erreur affichable si `file` sera forcément refusé, `null` sinon. */
export function validateProfileMediaFile(
  file: File,
  kind: ProfileMediaKind,
  constraints: ProfileMediaConstraints | null,
): string | null {
  if (file.size === 0) return 'Le fichier sélectionné est vide.';
  if (!constraints) return null;

  // `file.type` peut être vide sur certains navigateurs mobiles : dans ce
  // cas on laisse le serveur trancher plutôt que de refuser à tort.
  if (file.type !== '' && !constraints.acceptedMimeTypes.includes(file.type)) {
    return `${LABEL[kind]} doit être une image ${formatList(constraints.acceptedMimeTypes)}.`;
  }
  const maxBytes = constraints[kind].maxUploadBytes;
  if (file.size > maxBytes) {
    return `${LABEL[kind]} dépasse la taille maximale autorisée (${formatMegabytes(maxBytes)}).`;
  }
  return null;
}
