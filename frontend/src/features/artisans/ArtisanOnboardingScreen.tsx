import React, { useMemo, useState } from 'react';
import {
  CheckCircle2,
  Circle,
  FileText,
  MapPin,
  Plus,
  Trash2,
  UploadCloud,
  User,
  Wrench,
} from 'lucide-react';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SafeImage } from '../../components/ui/SafeImage';
import { Skeleton } from '../../components/ui/Skeleton';
import { formatFcfa } from '../../lib/format';
import { getCurrentPosition, type Coordinates } from '../../lib/geo';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { useCurrentUser } from '../profile/hooks/useCurrentUser';
import { VerificationStatusBanner } from './VerificationStatusBanner';
import { useArtisanProfileActions } from './hooks/useArtisanProfileActions';
import { useDocumentUpload } from './hooks/useDocumentUpload';
import { useMyArtisanProfile } from './hooks/useMyArtisanProfile';
import { useMyVerification } from './hooks/useMyVerification';
import { useTrades } from './hooks/useTrades';
import type { VerificationDocType, VerificationDocument, VerificationDocStatus } from '../../types';

const REQUIRED_DOCS: { type: VerificationDocType; label: string; hint: string }[] = [
  { type: 'cni', label: "Carte d'identité (CNI)", hint: 'Recto lisible — image ou PDF' },
  { type: 'selfie', label: 'Selfie', hint: 'Votre visage bien visible — image uniquement' },
];

const DOC_STATUS_LABEL: Record<VerificationDocStatus, string> = {
  pending: 'En attente de revue',
  approved: 'Validé',
  rejected: 'Refusé',
};

const DOC_STATUS_PILL: Record<VerificationDocStatus, string> = {
  pending: 'bg-accent-soft text-accent-foreground-strong',
  approved: 'bg-success text-success-foreground',
  rejected: 'bg-destructive-soft text-destructive',
};

function latestDocumentsByType(
  documents: VerificationDocument[],
): Partial<Record<VerificationDocType, VerificationDocument>> {
  const result: Partial<Record<VerificationDocType, VerificationDocument>> = {};
  for (const doc of documents) {
    const current = result[doc.docType];
    if (!current || new Date(doc.createdAt).getTime() > new Date(current.createdAt).getTime()) {
      result[doc.docType] = doc;
    }
  }
  return result;
}

const ChecklistItem: React.FC<{ done: boolean; label: string }> = ({ done, label }) => (
  <div className="flex items-center gap-2">
    {done ? (
      <CheckCircle2 className="w-5 h-5 text-success shrink-0" />
    ) : (
      <Circle className="w-5 h-5 text-white/40 shrink-0" />
    )}
    <span className={`text-sm font-sora ${done ? 'text-white' : 'text-primary-emerald-foreground'}`}>
      {label}
    </span>
  </div>
);

/**
 * Onboarding artisan (BUILD_PLAN.md, onboarding artisan §6) : profil,
 * métiers et documents de vérification en un seul parcours, avec une
 * checklist de progression et le bandeau de statut explicite (jamais un
 * artisan laissé à deviner pourquoi il ne reçoit pas de demandes).
 * Accessible depuis `/bienvenue-artisan` (première visite) et depuis `/pro`
 * (retour) tant que le compte n'est pas vérifié.
 */
export const ArtisanOnboardingScreen: React.FC = () => {
  const auth = useAuth();
  const role = toDisplayRole(auth.role);
  const { data: currentUser, isLoading: isUserLoading } = useCurrentUser();
  const artisanId = currentUser?.artisanId ?? null;

  const {
    data: profile,
    isLoading: isProfileLoading,
    error: profileError,
    reload: reloadProfile,
    setData: setProfile,
  } = useMyArtisanProfile(role === 'artisan' ? artisanId : null);
  const {
    data: verification,
    isLoading: isVerificationLoading,
    error: verificationError,
    reload: reloadVerification,
  } = useMyVerification(role === 'artisan' && artisanId != null);
  const { data: trades } = useTrades();

  const actions = useArtisanProfileActions((next) => setProfile(() => next));
  const documentUpload = useDocumentUpload(reloadVerification);

  const [bio, setBio] = useState('');
  const [yearsExperience, setYearsExperience] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [pendingLocation, setPendingLocation] = useState<Coordinates | null>(null);
  // Trace le profil déjà servi au formulaire, pas un booléen "initialisé" --
  // ajustement d'état pendant le rendu (pattern React officiel : "Adjusting
  // state when a prop changes"), volontairement PAS un useEffect : appeler
  // setState depuis un effet ici provoquerait un rendu supplémentaire
  // inutile (React bascule immédiatement sans jamais commiter le rendu
  // intermédiaire quand c'est fait pendant le rendu).
  const [loadedProfileId, setLoadedProfileId] = useState<string | null>(null);
  const [isLocating, setIsLocating] = useState(false);

  const [selectedTradeCode, setSelectedTradeCode] = useState('');
  const [hourlyRateFcfa, setHourlyRateFcfa] = useState('');
  const [radiusKm, setRadiusKm] = useState('');

  if (profile && profile.id !== loadedProfileId) {
    setLoadedProfileId(profile.id);
    setBio(profile.bio ?? '');
    setYearsExperience(profile.yearsExperience != null ? String(profile.yearsExperience) : '');
    setAvatarUrl(profile.avatarUrl ?? '');
  }

  const latestByType = useMemo(
    () => latestDocumentsByType(verification?.documents ?? []),
    [verification],
  );
  const hasProfileBasics = Boolean(
    profile?.bio && profile.bio.trim().length > 0 && profile.yearsExperience != null,
  );
  const hasTrades = Boolean(profile?.trades.length);
  const hasAllRequiredDocs = REQUIRED_DOCS.every(({ type }) => latestByType[type] != null);

  if (role !== 'artisan') {
    return (
      <main className="max-w-3xl mx-auto px-4 md:px-8 pt-6 pb-28">
        <EmptyState title="Cet espace est réservé aux artisans." />
      </main>
    );
  }

  if (!isUserLoading && !artisanId) {
    return (
      <main className="max-w-3xl mx-auto px-4 md:px-8 pt-6 pb-28">
        <EmptyState title="Aucun profil artisan n'est associé à ce compte." />
      </main>
    );
  }

  async function handleUseCurrentLocation(): Promise<void> {
    setIsLocating(true);
    try {
      const position = await getCurrentPosition();
      setPendingLocation(position);
    } finally {
      setIsLocating(false);
    }
  }

  async function handleSaveProfile(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    const trimmedBio = bio.trim();
    const trimmedAvatar = avatarUrl.trim();
    await actions.updateProfile({
      bio: trimmedBio === '' ? null : trimmedBio,
      yearsExperience: yearsExperience === '' ? null : Number(yearsExperience),
      avatarUrl: trimmedAvatar === '' ? null : trimmedAvatar,
      ...(pendingLocation ? { baseLocation: pendingLocation } : {}),
    });
    setPendingLocation(null);
  }

  async function handleAddTrade(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!selectedTradeCode || !hourlyRateFcfa || !radiusKm) return;
    const ok = await actions.addTrade({
      tradeCode: selectedTradeCode,
      hourlyRateFcfa: Number(hourlyRateFcfa),
      serviceRadiusM: Math.round(Number(radiusKm) * 1000),
    });
    if (ok) {
      setSelectedTradeCode('');
      setHourlyRateFcfa('');
      setRadiusKm('');
    }
  }

  function handleFileSelected(
    docType: VerificationDocType,
    event: React.ChangeEvent<HTMLInputElement>,
  ): void {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    void documentUpload.upload(docType, file);
  }

  async function handleAvatarFileSelected(
    event: React.ChangeEvent<HTMLInputElement>,
  ): Promise<void> {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const updated = await actions.uploadAvatar(file);
    if (updated) setAvatarUrl(updated.avatarUrl ?? '');
  }

  const declaredTradeCodes = new Set((profile?.trades ?? []).map((t) => t.tradeCode));
  const availableTrades = (trades ?? []).filter((t) => !declaredTradeCodes.has(t.code));

  return (
    <main className="pb-28">
      <section className="bg-primary text-white px-4 md:px-8 pt-6 pb-8 rounded-b-3xl">
        <div className="max-w-3xl mx-auto space-y-5">
          <div>
            <p className="font-sora text-xs uppercase tracking-wider text-primary-emerald-foreground">
              Espace Pro
            </p>
            <h1 className="font-headline-md text-2xl font-bold">Complétez votre profil</h1>
          </div>

          <div className="space-y-2">
            <ChecklistItem done={hasProfileBasics} label="Profil complété" />
            <ChecklistItem done={hasTrades} label="Métiers déclarés" />
            <ChecklistItem done={hasAllRequiredDocs} label="Documents envoyés" />
            <ChecklistItem
              done={profile?.verifiedStatus === 'verified'}
              label={
                profile?.verifiedStatus === 'verified' ? 'Compte vérifié' : 'Vérification en attente'
              }
            />
          </div>

          {profile && <VerificationStatusBanner status={profile.verifiedStatus} />}
        </div>
      </section>

      <div className="max-w-3xl mx-auto px-4 md:px-8 pt-6 space-y-6">
        {isProfileLoading && !profile ? (
          <div className="space-y-4">
            <Skeleton className="h-40 rounded-2xl" />
            <Skeleton className="h-40 rounded-2xl" />
          </div>
        ) : profileError && !profile ? (
          <ErrorState message={profileError.message} onRetry={reloadProfile} />
        ) : profile ? (
          <>
            <form
              onSubmit={handleSaveProfile}
              className="bg-white rounded-2xl p-5 border border-border-subtle space-y-4"
            >
              <h2 className="font-bold text-lg text-primary flex items-center gap-2">
                <User className="w-5 h-5" /> Mon profil
              </h2>

              <div className="flex flex-col items-center gap-3 pt-1 pb-2">
                <div className="w-24 h-24 rounded-full overflow-hidden border-2 border-border-subtle shrink-0 bg-surface-muted">
                  <SafeImage
                    src={avatarUrl || null}
                    fallback="/images/placeholder-avatar.svg"
                    alt="Photo de profil"
                    className="w-full h-full object-cover"
                  />
                </div>
                <label className="inline-flex items-center gap-2 py-2 px-4 rounded-full border-1.5 border-primary text-primary font-sora text-xs font-bold cursor-pointer hover:bg-primary/5 active:scale-95 transition-all">
                  <UploadCloud className="w-4 h-4" />
                  <span>{actions.isUploadingAvatar ? 'Envoi...' : 'Changer la photo'}</span>
                  <input
                    type="file"
                    accept="image/png,image/jpeg"
                    className="hidden"
                    disabled={actions.isUploadingAvatar}
                    onChange={handleAvatarFileSelected}
                  />
                </label>
                {actions.avatarError && (
                  <p className="text-xs text-destructive text-center">{actions.avatarError}</p>
                )}
                <details className="w-full text-center">
                  <summary className="text-[11px] font-sora text-muted-foreground-soft cursor-pointer">
                    Ou collez une URL d’image existante
                  </summary>
                  <input
                    id="onboarding-avatar-url"
                    type="url"
                    value={avatarUrl}
                    onChange={(e) => setAvatarUrl(e.target.value)}
                    placeholder="https://..."
                    className="mt-2 w-full p-3 rounded-xl border border-border-strong focus:border-primary focus:ring-1 focus:ring-primary text-sm outline-none"
                  />
                </details>
              </div>

              <div>
                <label htmlFor="onboarding-bio" className="text-xs font-sora font-bold text-muted-foreground-soft uppercase">
                  Bio
                </label>
                <textarea
                  id="onboarding-bio"
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  maxLength={2000}
                  rows={4}
                  placeholder="Présentez votre expérience, vos spécialités..."
                  className="mt-1 w-full p-3 rounded-xl border border-border-strong focus:border-primary focus:ring-1 focus:ring-primary text-sm outline-none resize-none"
                />
              </div>

              <div>
                <label htmlFor="onboarding-experience" className="text-xs font-sora font-bold text-muted-foreground-soft uppercase">
                  Années d’expérience
                </label>
                <input
                  id="onboarding-experience"
                  type="number"
                  min={0}
                  max={80}
                  value={yearsExperience}
                  onChange={(e) => setYearsExperience(e.target.value)}
                  className="mt-1 w-full p-3 rounded-xl border border-border-strong focus:border-primary focus:ring-1 focus:ring-primary text-sm outline-none"
                />
              </div>

              <button
                type="button"
                onClick={handleUseCurrentLocation}
                disabled={isLocating}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-full border-1.5 border-primary text-primary font-sora text-xs font-bold hover:bg-primary/5 active:scale-95 transition-all cursor-pointer disabled:opacity-60"
              >
                <MapPin className="w-4 h-4" />
                {isLocating
                  ? 'Localisation...'
                  : pendingLocation
                    ? 'Position mise à jour, prête à enregistrer'
                    : "Utiliser ma position actuelle"}
              </button>

              {actions.error && <p className="text-xs text-destructive">{actions.error}</p>}

              <button
                type="submit"
                disabled={actions.isSaving}
                className="w-full py-3 rounded-full bg-primary text-white font-sora text-sm font-bold hover:opacity-90 active:scale-95 transition-all cursor-pointer disabled:opacity-60"
              >
                {actions.isSaving ? 'Enregistrement...' : 'Enregistrer mon profil'}
              </button>
            </form>

            <section className="bg-white rounded-2xl p-5 border border-border-subtle space-y-4">
              <h2 className="font-bold text-lg text-primary flex items-center gap-2">
                <Wrench className="w-5 h-5" /> Mes métiers
              </h2>

              {profile.trades.length === 0 ? (
                <p className="text-sm text-muted-foreground-soft">Aucun métier déclaré pour le moment.</p>
              ) : (
                <ul className="space-y-2">
                  {profile.trades.map((trade) => (
                    <li
                      key={trade.id}
                      className="flex items-center justify-between gap-3 p-3 rounded-xl bg-surface-muted"
                    >
                      <div>
                        <p className="font-sora text-sm font-bold text-foreground">{trade.tradeLabel}</p>
                        <p className="text-xs text-muted-foreground-soft">
                          {formatFcfa(trade.hourlyRateFcfa)}/h · rayon {(trade.serviceRadiusM / 1000).toFixed(1)} km
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => actions.removeTrade(trade.id)}
                        disabled={actions.isSaving}
                        aria-label={`Retirer ${trade.tradeLabel}`}
                        className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-destructive-soft transition-colors cursor-pointer disabled:opacity-60"
                      >
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {availableTrades.length > 0 && (
                <form onSubmit={handleAddTrade} className="space-y-3 pt-3 border-t border-border-faint">
                  <select
                    value={selectedTradeCode}
                    onChange={(e) => setSelectedTradeCode(e.target.value)}
                    className="w-full p-3 rounded-xl border border-border-strong text-sm outline-none focus:border-primary"
                  >
                    <option value="">Choisir un métier</option>
                    {availableTrades.map((trade) => (
                      <option key={trade.code} value={trade.code}>
                        {trade.labelFr}
                      </option>
                    ))}
                  </select>
                  <div className="flex gap-3">
                    <input
                      type="number"
                      min={0}
                      value={hourlyRateFcfa}
                      onChange={(e) => setHourlyRateFcfa(e.target.value)}
                      placeholder="Tarif horaire (FCFA)"
                      className="flex-1 p-3 rounded-xl border border-border-strong text-sm outline-none focus:border-primary"
                    />
                    <input
                      type="number"
                      min={0.1}
                      step={0.1}
                      value={radiusKm}
                      onChange={(e) => setRadiusKm(e.target.value)}
                      placeholder="Rayon (km)"
                      className="flex-1 p-3 rounded-xl border border-border-strong text-sm outline-none focus:border-primary"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={actions.isSaving || !selectedTradeCode || !hourlyRateFcfa || !radiusKm}
                    className="w-full flex items-center justify-center gap-2 py-2.5 rounded-full border-1.5 border-primary text-primary font-sora text-xs font-bold hover:bg-primary/5 active:scale-95 transition-all cursor-pointer disabled:opacity-60"
                  >
                    <Plus className="w-4 h-4" /> Ajouter ce métier
                  </button>
                </form>
              )}
            </section>
          </>
        ) : null}

        <section className="bg-white rounded-2xl p-5 border border-border-subtle space-y-4">
          <h2 className="font-bold text-lg text-primary flex items-center gap-2">
            <FileText className="w-5 h-5" /> Documents de vérification
          </h2>

          {isVerificationLoading && !verification ? (
            <Skeleton className="h-32 rounded-2xl" />
          ) : verificationError && !verification ? (
            <ErrorState message={verificationError.message} onRetry={reloadVerification} />
          ) : (
            REQUIRED_DOCS.map(({ type, label, hint }) => {
              const doc = latestByType[type];
              const uploadState = documentUpload.stateFor(type);
              return (
                <div key={type} className="p-3 rounded-xl border border-border-subtle space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="font-sora text-sm font-bold text-foreground">{label}</p>
                      <p className="text-xs text-muted-foreground-soft">{hint}</p>
                    </div>
                    {doc && (
                      <span
                        className={`text-xs font-sora font-bold px-2 py-1 rounded-full shrink-0 ${DOC_STATUS_PILL[doc.status]}`}
                      >
                        {DOC_STATUS_LABEL[doc.status]}
                      </span>
                    )}
                  </div>

                  {doc?.status === 'rejected' && doc.note && (
                    <p className="text-xs text-destructive">Motif : {doc.note}</p>
                  )}

                  <label className="inline-flex items-center gap-2 py-2 px-4 rounded-full border-1.5 border-primary text-primary font-sora text-xs font-bold cursor-pointer hover:bg-primary/5 active:scale-95 transition-all">
                    <UploadCloud className="w-4 h-4" />
                    <span>
                      {uploadState.isUploading ? 'Envoi...' : doc ? 'Renvoyer un document' : 'Envoyer un document'}
                    </span>
                    <input
                      type="file"
                      accept="image/png,image/jpeg,application/pdf"
                      className="hidden"
                      disabled={uploadState.isUploading}
                      onChange={(e) => handleFileSelected(type, e)}
                    />
                  </label>

                  {uploadState.error && <p className="text-xs text-destructive">{uploadState.error}</p>}
                </div>
              );
            })
          )}
        </section>
      </div>
    </main>
  );
};
