import { useState } from 'react';
import { ApiError, api } from '../../../lib/api';
import type { AddArtisanTradeInput, UpdateArtisanProfileInput } from '../../../lib/api/types';
import type { MyArtisanProfile, ProfileMediaConstraints } from '../../../types';
import { validateProfileMediaFile, type ProfileMediaKind } from '../profileMedia';

function toMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.';
}

interface MediaUploadState {
  isUploading: boolean;
  error: string | null;
}

const IDLE_MEDIA_STATE: MediaUploadState = { isUploading: false, error: null };

/**
 * Regroupe les mutations de l'onboarding qui renvoient toutes la même
 * forme `MyArtisanProfile` (édition du profil, ajout/retrait d'un métier,
 * envoi de l'avatar ou de la couverture) — `onUpdated` est censé alimenter
 * le `useMyArtisanProfile().setData` de l'appelant, pour que toutes restent
 * synchronisées sur une seule source de vérité plutôt que plusieurs copies
 * indépendantes du profil. `mediaConstraints` (serveur, `null` tant que non
 * chargées) alimente le pré-contrôle local des photos.
 */
export function useArtisanProfileActions(
  onUpdated: (profile: MyArtisanProfile) => void,
  mediaConstraints: ProfileMediaConstraints | null = null,
) {
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Un état par média, distinct de isSaving/error ci-dessus : chaque upload
  // se déclenche depuis son propre contrôle (input file), indépendant du
  // formulaire bio/expérience -- un envoi de couverture en cours ne doit
  // griser ni le bouton "Enregistrer mon profil" ni celui de l'avatar, et
  // une erreur sur l'un ne doit jamais s'afficher sous l'autre.
  const [media, setMedia] = useState<Record<ProfileMediaKind, MediaUploadState>>({
    avatar: IDLE_MEDIA_STATE,
    cover: IDLE_MEDIA_STATE,
  });

  function setMediaState(kind: ProfileMediaKind, next: MediaUploadState): void {
    setMedia((current) => ({ ...current, [kind]: next }));
  }

  async function run(action: () => Promise<MyArtisanProfile>): Promise<boolean> {
    setError(null);
    setIsSaving(true);
    try {
      const profile = await action();
      onUpdated(profile);
      return true;
    } catch (err) {
      setError(toMessage(err));
      return false;
    } finally {
      setIsSaving(false);
    }
  }

  // Renvoie le profil à jour (pas juste un booléen comme `run` ci-dessus) :
  // l'appelant garde localement une copie éditable de l'URL (champ URL
  // manuel) qui ne se resynchronise pas toute seule au contenu du profil
  // (seulement à son id, pour ne pas écraser une saisie en cours) -- il a
  // donc besoin de la nouvelle valeur explicitement pour l'y refléter.
  async function uploadMedia(kind: ProfileMediaKind, file: File): Promise<MyArtisanProfile | null> {
    // Refus local immédiat d'un fichier que le serveur rejetterait de toute
    // façon (voir profileMedia.ts) -- aucune requête, aucun budget consommé.
    const localError = validateProfileMediaFile(file, kind, mediaConstraints);
    if (localError) {
      setMediaState(kind, { isUploading: false, error: localError });
      return null;
    }

    setMediaState(kind, { isUploading: true, error: null });
    try {
      const profile = kind === 'avatar' ? await api.uploadAvatar(file) : await api.uploadCover(file);
      onUpdated(profile);
      setMediaState(kind, IDLE_MEDIA_STATE);
      return profile;
    } catch (err) {
      setMediaState(kind, { isUploading: false, error: toMessage(err) });
      return null;
    }
  }

  return {
    isSaving,
    error,
    isUploadingAvatar: media.avatar.isUploading,
    avatarError: media.avatar.error,
    isUploadingCover: media.cover.isUploading,
    coverError: media.cover.error,
    updateProfile: (input: UpdateArtisanProfileInput) =>
      run(() => api.updateMyArtisanProfile(input)),
    uploadAvatar: (file: File) => uploadMedia('avatar', file),
    uploadCover: (file: File) => uploadMedia('cover', file),
    addTrade: (input: AddArtisanTradeInput) => run(() => api.addArtisanTrade(input)),
    removeTrade: (artisanTradeId: string) => run(() => api.removeArtisanTrade(artisanTradeId)),
  };
}
