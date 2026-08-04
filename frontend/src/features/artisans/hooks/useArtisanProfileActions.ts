import { useState } from 'react';
import { ApiError, api } from '../../../lib/api';
import type { AddArtisanTradeInput, UpdateArtisanProfileInput } from '../../../lib/api/types';
import type { MyArtisanProfile } from '../../../types';

function toMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.';
}

/**
 * Regroupe les trois mutations de l'onboarding qui renvoient toutes la même
 * forme `MyArtisanProfile` (édition du profil, ajout/retrait d'un métier)
 * derrière un seul état saving/error — `onUpdated` est censé alimenter le
 * `useMyArtisanProfile().setData` de l'appelant, pour que les trois restent
 * synchronisées sur une seule source de vérité plutôt que trois copies
 * indépendantes du profil.
 */
export function useArtisanProfileActions(onUpdated: (profile: MyArtisanProfile) => void) {
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // État distinct de isSaving/error ci-dessus : l'upload de la photo se
  // déclenche depuis son propre contrôle (input file), indépendant du
  // formulaire bio/expérience -- un upload en cours ne doit pas griser le
  // bouton "Enregistrer mon profil", et réciproquement.
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const [avatarError, setAvatarError] = useState<string | null>(null);

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
  // l'appelant garde localement une copie éditable de `avatarUrl` (champ URL
  // manuel) qui ne se resynchronise pas toute seule au contenu du profil
  // (seulement à son id, pour ne pas écraser une saisie en cours) -- il a
  // donc besoin de la nouvelle valeur explicitement pour l'y refléter.
  async function uploadAvatar(file: File): Promise<MyArtisanProfile | null> {
    setAvatarError(null);
    setIsUploadingAvatar(true);
    try {
      const profile = await api.uploadAvatar(file);
      onUpdated(profile);
      return profile;
    } catch (err) {
      setAvatarError(toMessage(err));
      return null;
    } finally {
      setIsUploadingAvatar(false);
    }
  }

  return {
    isSaving,
    error,
    isUploadingAvatar,
    avatarError,
    updateProfile: (input: UpdateArtisanProfileInput) =>
      run(() => api.updateMyArtisanProfile(input)),
    uploadAvatar,
    addTrade: (input: AddArtisanTradeInput) => run(() => api.addArtisanTrade(input)),
    removeTrade: (artisanTradeId: string) => run(() => api.removeArtisanTrade(artisanTradeId)),
  };
}
