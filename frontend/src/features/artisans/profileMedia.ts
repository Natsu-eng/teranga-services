// Contraintes des médias publics du profil artisan (avatar, couverture),
// alignées sur le backend (`AVATAR_MAX_UPLOAD_BYTES` / `COVER_MAX_UPLOAD_BYTES`,
// `ALLOWED_MEDIA_TYPES` dans app/services/profile_media.py).
//
// Simple pré-contrôle d'ergonomie : il évite d'envoyer 10 Mo sur une
// connexion mobile lente pour se faire refuser ensuite, et ne consomme pas
// le budget d'envois partagé (rate limiting) pour un fichier voué à l'échec.
// Le serveur reste la seule vraie barrière : il revérifie le type par le
// CONTENU du fichier (magic bytes), pas par son type MIME déclaré.

export type ProfileMediaKind = 'avatar' | 'cover';

export const PROFILE_MEDIA_MAX_BYTES = 4 * 1024 * 1024;

export const PROFILE_MEDIA_ACCEPT = 'image/png,image/jpeg';

const ALLOWED_MIME_TYPES = new Set(['image/png', 'image/jpeg']);

const LABEL: Record<ProfileMediaKind, string> = {
  avatar: 'La photo de profil',
  cover: 'La photo de couverture',
};

/** Message d'erreur affichable si `file` sera forcément refusé, `null` sinon. */
export function validateProfileMediaFile(file: File, kind: ProfileMediaKind): string | null {
  if (file.size === 0) return 'Le fichier sélectionné est vide.';
  // `file.type` peut être vide sur certains navigateurs mobiles : dans ce
  // cas on laisse le serveur trancher plutôt que de refuser à tort.
  if (file.type !== '' && !ALLOWED_MIME_TYPES.has(file.type)) {
    return `${LABEL[kind]} doit être une image JPEG ou PNG.`;
  }
  if (file.size > PROFILE_MEDIA_MAX_BYTES) {
    const maxMo = PROFILE_MEDIA_MAX_BYTES / (1024 * 1024);
    return `${LABEL[kind]} dépasse la taille maximale autorisée (${maxMo} Mo).`;
  }
  return null;
}
