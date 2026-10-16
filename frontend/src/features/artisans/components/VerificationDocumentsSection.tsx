import React from 'react';
import { FileText, UploadCloud } from 'lucide-react';
import { Card } from '../../../components/ui/Card';
import { ErrorState } from '../../../components/ui/ErrorState';
import { Skeleton } from '../../../components/ui/Skeleton';
import { StatusPill } from '../../../components/ui/StatusPill';
import { buttonClasses } from '../../../components/ui/styles';
import type { ApiError } from '../../../lib/api';
import { cn } from '../../../lib/cn';
import type { MyVerification, VerificationDocType, VerificationDocument } from '../../../types';
import type { useDocumentUpload } from '../hooks/useDocumentUpload';
import { DOC_STATUS, REQUIRED_DOCS } from '../onboardingDocuments';

interface VerificationDocumentsSectionProps {
  isVerificationLoading: boolean;
  verification: MyVerification | null;
  verificationError: ApiError | null;
  reloadVerification: () => void;
  latestByType: Partial<Record<VerificationDocType, VerificationDocument>>;
  documentUpload: ReturnType<typeof useDocumentUpload>;
  handleFileSelected: (
    docType: VerificationDocType,
    event: React.ChangeEvent<HTMLInputElement>,
  ) => void;
}

/**
 * Section « Documents de vérification » de l'onboarding artisan : statut
 * de chaque document requis, motif d'un refus, envoi ou renvoi. Extraite
 * de `ArtisanOnboardingScreen.tsx` sans changement de rendu ni de logique
 * (les props portent les noms des variables d'origine).
 */
export const VerificationDocumentsSection: React.FC<VerificationDocumentsSectionProps> = ({
  isVerificationLoading,
  verification,
  verificationError,
  reloadVerification,
  latestByType,
  documentUpload,
  handleFileSelected,
}) => (
  <Card as="section" padding="lg" aria-labelledby="onboarding-documents" className="space-y-4">
    <div className="space-y-1">
      <h2
        id="onboarding-documents"
        className="font-display text-display-sm font-semibold text-primary flex items-center gap-2"
      >
        <FileText aria-hidden className="w-5 h-5" /> Documents de vérification
      </h2>
      <p className="text-sm text-muted-foreground">
        Vos documents restent privés : seule l&apos;équipe Téranga les consulte pour vérifier votre
        identité.
      </p>
    </div>

    {isVerificationLoading && !verification ? (
      <Skeleton className="h-32 rounded-field" />
    ) : verificationError && !verification ? (
      <ErrorState message={verificationError.message} onRetry={reloadVerification} />
    ) : (
      <ul className="space-y-3">
        {REQUIRED_DOCS.map(({ type, label, hint }) => {
          const doc = latestByType[type];
          const uploadState = documentUpload.stateFor(type);
          return (
            <li key={type} className="rounded-field bg-surface-muted p-3 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground">{label}</p>
                  <p className="text-sm text-muted-foreground">{hint}</p>
                </div>
                {doc && (
                  <StatusPill tone={DOC_STATUS[doc.status].tone}>
                    {DOC_STATUS[doc.status].label}
                  </StatusPill>
                )}
              </div>

              {doc?.status === 'rejected' && doc.note && (
                <p className="text-sm text-destructive">Motif : {doc.note}</p>
              )}

              <label
                className={cn(
                  buttonClasses({ variant: 'outline', size: 'sm' }),
                  'focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary-emerald',
                )}
              >
                <UploadCloud aria-hidden className="w-4 h-4" />
                <span>
                  {uploadState.isUploading
                    ? 'Envoi...'
                    : doc
                      ? 'Renvoyer un document'
                      : 'Envoyer un document'}
                </span>
                {/* sr-only (et non hidden) : atteignable au clavier, nommé
                      pour les lecteurs d'écran. */}
                <input
                  type="file"
                  accept="image/png,image/jpeg,application/pdf"
                  aria-label={`Envoyer : ${label}`}
                  className="sr-only"
                  disabled={uploadState.isUploading}
                  onChange={(e) => handleFileSelected(type, e)}
                />
              </label>

              {uploadState.error && (
                <p role="alert" className="text-sm text-destructive">
                  {uploadState.error}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    )}
  </Card>
);
