import React, { useMemo, useState } from 'react';
import { Camera, MapPin, Plus, Trash2, UploadCloud, UserRound, Wrench } from 'lucide-react';
import { RoleRestricted } from '../../components/auth/RoleRestricted';
import { AppBar } from '../../components/ui/AppBar';
import { Avatar } from '../../components/ui/Avatar';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SelectField, TextAreaField, TextField } from '../../components/ui/Field';
import { IconButton } from '../../components/ui/IconButton';
import { SafeImage } from '../../components/ui/SafeImage';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { Skeleton } from '../../components/ui/Skeleton';
import { buttonClasses } from '../../components/ui/styles';
import { cn } from '../../lib/cn';
import { formatFcfa } from '../../lib/format';
import { GeolocationError, getCurrentPosition, type Coordinates } from '../../lib/geo';
import { useAuth } from '../auth/hooks/useAuth';
import { toDisplayRole } from '../auth/role';
import { useCurrentUser } from '../profile/hooks/useCurrentUser';
import { VerificationStatusBanner } from './VerificationStatusBanner';
import { ChecklistItem } from './components/OnboardingChecklistItem';
import { VerificationDocumentsSection } from './components/VerificationDocumentsSection';
import { REQUIRED_DOCS, latestDocumentsByType } from './onboardingDocuments';
import { acceptAttribute, constraintsHint } from './profileMedia';
import { useArtisanProfileActions } from './hooks/useArtisanProfileActions';
import { useDocumentUpload } from './hooks/useDocumentUpload';
import { useMyArtisanProfile } from './hooks/useMyArtisanProfile';
import { useProfileMediaConstraints } from './hooks/useProfileMediaConstraints';
import { useMyVerification } from './hooks/useMyVerification';
import { useTrades } from './hooks/useTrades';
import type { VerificationDocType } from '../../types';

/**
 * Onboarding artisan (/pro/onboarding) : profil, métiers et documents de
 * vérification en un seul parcours, avec une checklist de progression sur
 * le bandeau vert profond de l'espace Pro et le statut de vérification
 * toujours visible (jamais un artisan laissé à deviner pourquoi il ne
 * reçoit pas de demandes). C'est aussi l'écran d'édition complète du
 * profil Pro, accessible depuis le profil et la fiche publique.
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

  const mediaConstraints = useProfileMediaConstraints(role === 'artisan' && artisanId != null);
  const actions = useArtisanProfileActions((next) => setProfile(() => next), mediaConstraints);
  const mediaHint = constraintsHint(mediaConstraints);
  const documentUpload = useDocumentUpload(reloadVerification);

  const [fullName, setFullName] = useState('');
  const [bio, setBio] = useState('');
  const [yearsExperience, setYearsExperience] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [coverUrl, setCoverUrl] = useState('');
  const [pendingLocation, setPendingLocation] = useState<Coordinates | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
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
    setFullName(profile.fullName);
    setBio(profile.bio ?? '');
    setYearsExperience(profile.yearsExperience != null ? String(profile.yearsExperience) : '');
    setAvatarUrl(profile.avatarUrl ?? '');
    setCoverUrl(profile.coverUrl ?? '');
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
  const isVerified = profile?.verifiedStatus === 'verified';
  const doneCount = [hasProfileBasics, hasTrades, hasAllRequiredDocs, isVerified].filter(
    Boolean,
  ).length;

  // Défense en profondeur : la route est déjà réservée aux artisans.
  if (role !== 'artisan') {
    return <RoleRestricted reservedFor="artisan" currentRole={auth.role} />;
  }

  if (!isUserLoading && !artisanId) {
    return (
      <main className="max-w-3xl mx-auto px-4 md:px-8 pt-6">
        <EmptyState title="Aucun profil artisan n'est associé à ce compte." />
      </main>
    );
  }

  async function handleUseCurrentLocation(): Promise<void> {
    setIsLocating(true);
    setLocationError(null);
    try {
      const position = await getCurrentPosition();
      setPendingLocation(position);
    } catch (err) {
      // Jamais de position de repli silencieuse : la zone d'intervention en
      // dépend, l'artisan doit savoir qu'elle n'a pas été mise à jour.
      setLocationError(
        `${err instanceof GeolocationError ? err.message : "Votre position n'a pas pu être déterminée."} Votre position enregistrée n'a pas changé.`,
      );
    } finally {
      setIsLocating(false);
    }
  }

  async function handleSaveProfile(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    const trimmedBio = bio.trim();
    const trimmedAvatar = avatarUrl.trim();
    const trimmedCover = coverUrl.trim();
    await actions.updateProfile({
      fullName: fullName.trim(),
      bio: trimmedBio === '' ? null : trimmedBio,
      yearsExperience: yearsExperience === '' ? null : Number(yearsExperience),
      avatarUrl: trimmedAvatar === '' ? null : trimmedAvatar,
      coverUrl: trimmedCover === '' ? null : trimmedCover,
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

  async function handleCoverFileSelected(
    event: React.ChangeEvent<HTMLInputElement>,
  ): Promise<void> {
    const file = event.target.files?.[0];
    // Réinitialisé tout de suite : resélectionner le MÊME fichier après une
    // erreur doit redéclencher `onChange` (sinon le navigateur l'ignore).
    event.target.value = '';
    if (!file) return;
    const updated = await actions.uploadCover(file);
    if (updated) setCoverUrl(updated.coverUrl ?? '');
  }

  const declaredTradeCodes = new Set((profile?.trades ?? []).map((t) => t.tradeCode));
  const availableTrades = (trades ?? []).filter((t) => !declaredTradeCodes.has(t.code));

  return (
    <>
      <AppBar title="Mon profil Pro" backTo="/pro" tone="pro" />

      <section
        data-tone="dark"
        className="bg-primary text-white px-4 md:px-8 pt-2 pb-8 rounded-b-sheet"
      >
        <div className="max-w-3xl mx-auto space-y-5">
          <SectionHeader
            tone="on-dark"
            title="Complétez votre profil"
            description="Un profil complet et vérifié inspire confiance et vous rend visible des clients."
          />

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-primary-emerald-foreground">Progression</span>
              <span className="font-semibold">{doneCount} / 4</span>
            </div>
            <div
              role="progressbar"
              aria-label="Progression du profil"
              aria-valuemin={0}
              aria-valuemax={4}
              aria-valuenow={doneCount}
              className="h-2 rounded-full bg-white/15 overflow-hidden"
            >
              <div
                className="h-full rounded-full bg-accent transition-[width] duration-300"
                style={{ width: `${(doneCount / 4) * 100}%` }}
              />
            </div>
          </div>

          <ul className="space-y-2.5">
            <ChecklistItem done={hasProfileBasics} label="Profil complété" />
            <ChecklistItem done={hasTrades} label="Métiers déclarés" />
            <ChecklistItem done={hasAllRequiredDocs} label="Documents envoyés" />
            <ChecklistItem
              done={isVerified}
              label={isVerified ? 'Compte vérifié' : 'Vérification en attente'}
            />
          </ul>

          {profile && <VerificationStatusBanner status={profile.verifiedStatus} />}
        </div>
      </section>

      <main className="w-full max-w-3xl mx-auto px-4 md:px-8 pt-6 pb-12 space-y-6">
        {isProfileLoading && !profile ? (
          <div className="space-y-4" aria-busy="true">
            <Skeleton className="h-64 rounded-card" />
            <Skeleton className="h-40 rounded-card" />
          </div>
        ) : profileError && !profile ? (
          <ErrorState message={profileError.message} onRetry={reloadProfile} />
        ) : profile ? (
          <>
            <Card
              as="section"
              padding="lg"
              aria-labelledby="onboarding-profil"
              className="space-y-5"
            >
              <h2
                id="onboarding-profil"
                className="font-display text-display-sm font-semibold text-primary flex items-center gap-2"
              >
                <UserRound aria-hidden className="w-5 h-5" /> Mon profil
              </h2>

              <form onSubmit={handleSaveProfile} className="space-y-5">
                {/* Aperçu fidèle à la fiche publique : couverture, avatar en
                    chevauchement. Chaque photo a son bouton, son état d'envoi
                    et son message d'erreur. */}
                <div className="space-y-3">
                  <div className="relative">
                    <div className="h-32 md:h-40 rounded-field overflow-hidden bg-surface-muted">
                      <SafeImage
                        src={coverUrl || null}
                        fallback="/images/placeholder-cover.svg"
                        alt="Photo de couverture"
                        className={cn(
                          'w-full h-full object-cover transition-opacity',
                          actions.isUploadingCover && 'opacity-50',
                        )}
                      />
                    </div>
                    <label
                      className={cn(
                        buttonClasses({ variant: 'outline', size: 'sm' }),
                        'absolute top-2 right-2 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary-emerald',
                      )}
                    >
                      <Camera aria-hidden className="w-4 h-4" />
                      <span>{actions.isUploadingCover ? 'Envoi...' : 'Couverture'}</span>
                      <input
                        type="file"
                        accept={acceptAttribute(mediaConstraints)}
                        aria-label="Photo de couverture"
                        className="sr-only"
                        disabled={actions.isUploadingCover}
                        onChange={handleCoverFileSelected}
                      />
                    </label>
                    <div className="absolute -bottom-10 left-1/2 -translate-x-1/2 rounded-full ring-4 ring-surface">
                      <Avatar
                        name={fullName}
                        src={avatarUrl || null}
                        size="xl"
                        decorative
                        className={actions.isUploadingAvatar ? 'opacity-50' : undefined}
                      />
                    </div>
                  </div>

                  <div className="flex flex-col items-center gap-2 pt-11">
                    <label
                      className={cn(
                        buttonClasses({ variant: 'outline', size: 'sm' }),
                        'focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary-emerald',
                      )}
                    >
                      <UploadCloud aria-hidden className="w-4 h-4" />
                      <span>{actions.isUploadingAvatar ? 'Envoi...' : 'Changer la photo'}</span>
                      <input
                        type="file"
                        accept={acceptAttribute(mediaConstraints)}
                        aria-label="Photo de profil"
                        className="sr-only"
                        disabled={actions.isUploadingAvatar}
                        onChange={handleAvatarFileSelected}
                      />
                    </label>
                    {mediaHint && <p className="text-xs text-muted-foreground">{mediaHint}</p>}
                    {actions.coverError && (
                      <p role="alert" className="text-sm text-destructive text-center">
                        {actions.coverError}
                      </p>
                    )}
                    {actions.avatarError && (
                      <p role="alert" className="text-sm text-destructive text-center">
                        {actions.avatarError}
                      </p>
                    )}
                  </div>

                  <details className="w-full rounded-field bg-surface-muted px-3 py-2">
                    <summary className="text-sm text-muted-foreground cursor-pointer">
                      Ou collez des URL d’images existantes
                    </summary>
                    <div className="mt-3 space-y-3">
                      <TextField
                        id="onboarding-avatar-url"
                        label="URL de la photo de profil"
                        type="url"
                        value={avatarUrl}
                        onChange={(e) => setAvatarUrl(e.target.value)}
                        placeholder="https://..."
                      />
                      <TextField
                        id="onboarding-cover-url"
                        label="URL de la photo de couverture"
                        type="url"
                        value={coverUrl}
                        onChange={(e) => setCoverUrl(e.target.value)}
                        placeholder="https://..."
                      />
                    </div>
                  </details>
                </div>

                <TextField
                  id="onboarding-full-name"
                  label="Nom complet"
                  type="text"
                  autoComplete="name"
                  minLength={2}
                  maxLength={150}
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  hint="Affiché sur votre fiche publique."
                />

                <TextAreaField
                  id="onboarding-bio"
                  label="Présentation"
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  maxLength={2000}
                  rows={4}
                  placeholder="Présentez votre expérience, vos spécialités..."
                />

                <TextField
                  id="onboarding-experience"
                  label="Années d’expérience"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={80}
                  value={yearsExperience}
                  onChange={(e) => setYearsExperience(e.target.value)}
                />

                <Button
                  variant="outline"
                  fullWidth
                  onClick={handleUseCurrentLocation}
                  isLoading={isLocating}
                  leadingIcon={<MapPin aria-hidden className="w-4 h-4" />}
                >
                  {isLocating
                    ? 'Localisation...'
                    : pendingLocation
                      ? 'Position mise à jour, prête à enregistrer'
                      : 'Utiliser ma position actuelle'}
                </Button>
                {locationError && (
                  <p role="alert" className="text-sm text-destructive">
                    {locationError}
                  </p>
                )}

                {actions.error && (
                  <p role="alert" className="text-sm text-destructive">
                    {actions.error}
                  </p>
                )}

                <Button
                  type="submit"
                  variant="brand"
                  size="lg"
                  fullWidth
                  isLoading={actions.isSaving}
                >
                  {actions.isSaving ? 'Enregistrement...' : 'Enregistrer mon profil'}
                </Button>
              </form>
            </Card>

            <Card
              as="section"
              padding="lg"
              aria-labelledby="onboarding-metiers"
              className="space-y-4"
            >
              <h2
                id="onboarding-metiers"
                className="font-display text-display-sm font-semibold text-primary flex items-center gap-2"
              >
                <Wrench aria-hidden className="w-5 h-5" /> Mes métiers
              </h2>

              {profile.trades.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Aucun métier déclaré pour le moment.
                </p>
              ) : (
                <ul className="space-y-2">
                  {profile.trades.map((trade) => (
                    <li
                      key={trade.id}
                      className="flex items-center justify-between gap-3 rounded-field bg-emerald-tint px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-foreground">{trade.tradeLabel}</p>
                        <p className="text-sm text-muted-foreground">
                          {formatFcfa(trade.hourlyRateFcfa)}/h · rayon{' '}
                          {(trade.serviceRadiusM / 1000).toFixed(1)} km
                        </p>
                      </div>
                      <IconButton
                        label={`Retirer ${trade.tradeLabel}`}
                        onClick={() => actions.removeTrade(trade.id)}
                        disabled={actions.isSaving}
                        tone="danger"
                      >
                        <Trash2 aria-hidden className="w-4 h-4" />
                      </IconButton>
                    </li>
                  ))}
                </ul>
              )}

              {availableTrades.length > 0 && (
                <form
                  onSubmit={handleAddTrade}
                  className="space-y-3 pt-4 border-t border-border-faint"
                >
                  <SelectField
                    label="Ajouter un métier"
                    value={selectedTradeCode}
                    onChange={(e) => setSelectedTradeCode(e.target.value)}
                  >
                    <option value="">Choisir un métier</option>
                    {availableTrades.map((trade) => (
                      <option key={trade.code} value={trade.code}>
                        {trade.labelFr}
                      </option>
                    ))}
                  </SelectField>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <TextField
                      label="Tarif horaire"
                      type="number"
                      inputMode="numeric"
                      min={0}
                      value={hourlyRateFcfa}
                      onChange={(e) => setHourlyRateFcfa(e.target.value)}
                      placeholder="Tarif horaire (FCFA)"
                    />
                    <TextField
                      label="Rayon d’intervention"
                      type="number"
                      inputMode="decimal"
                      min={0.1}
                      step={0.1}
                      value={radiusKm}
                      onChange={(e) => setRadiusKm(e.target.value)}
                      placeholder="Rayon (km)"
                    />
                  </div>
                  <Button
                    type="submit"
                    variant="outline"
                    fullWidth
                    disabled={
                      actions.isSaving || !selectedTradeCode || !hourlyRateFcfa || !radiusKm
                    }
                    leadingIcon={<Plus aria-hidden className="w-4 h-4" />}
                  >
                    Ajouter ce métier
                  </Button>
                </form>
              )}
            </Card>
          </>
        ) : null}

        <VerificationDocumentsSection
          isVerificationLoading={isVerificationLoading}
          verification={verification}
          verificationError={verificationError}
          reloadVerification={reloadVerification}
          latestByType={latestByType}
          documentUpload={documentUpload}
          handleFileSelected={handleFileSelected}
        />
      </main>
    </>
  );
};
