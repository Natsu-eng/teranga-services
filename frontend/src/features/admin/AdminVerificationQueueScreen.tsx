import React, { useState } from 'react';
import { Eye, FileText, LogOut, ShieldCheck } from 'lucide-react';
import { Avatar } from '../../components/ui/Avatar';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { TextAreaField } from '../../components/ui/Field';
import { Logo } from '../../components/ui/Logo';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { useAuth } from '../auth/hooks/useAuth';
import { useAdminVerificationQueue } from './hooks/useAdminVerificationQueue';
import { useDocumentPreview } from './hooks/useDocumentPreview';
import { useVerificationReview } from './hooks/useVerificationReview';
import type { AdminVerificationListItem, VerificationDocType } from '../../types';

const DOC_TYPE_LABEL: Record<VerificationDocType, string> = {
  cni: "Carte d'identité (CNI)",
  selfie: 'Selfie',
  accreditation: 'Accréditation métier',
  address_proof: 'Justificatif de domicile',
};

/** Longueur minimale du motif de rejet (alignée sur la validation serveur). */
const MIN_NOTE_LENGTH = 3;

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface VerificationCardProps {
  item: AdminVerificationListItem;
  onReviewed: (verificationId: string) => void;
}

const VerificationCard: React.FC<VerificationCardProps> = ({ item, onReviewed }) => {
  const preview = useDocumentPreview();
  const review = useVerificationReview(onReviewed);
  const [isRejecting, setIsRejecting] = useState(false);
  const [note, setNote] = useState('');

  const isBusy = review.pendingAction?.verificationId === item.id;
  const isApproving = isBusy && review.pendingAction?.kind === 'approve';
  const isSubmittingReject = isBusy && review.pendingAction?.kind === 'reject';
  const documentPreview = preview.previews[item.id];
  const isLoadingPreview = preview.loadingId === item.id;
  const isNoteValid = note.trim().length >= MIN_NOTE_LENGTH;

  async function handleConfirmReject(): Promise<void> {
    if (!isNoteValid) return;
    const result = await review.reject(item.id, note.trim());
    if (result) {
      setIsRejecting(false);
      setNote('');
    }
  }

  return (
    <Card as="article" padding="lg" className="space-y-4">
      <div className="flex items-start gap-3">
        <Avatar name={item.artisanFullName} size="sm" decorative />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-foreground truncate">{item.artisanFullName}</p>
          <p className="text-sm text-muted-foreground">
            {DOC_TYPE_LABEL[item.docType]} · déposé le {formatDateTime(item.createdAt)}
          </p>
        </div>
        <StatusPill tone="warning">À vérifier</StatusPill>
      </div>

      <div className="rounded-field bg-surface-muted p-3">
        {documentPreview ? (
          documentPreview.isPdf ? (
            <a
              href={documentPreview.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 text-sm font-semibold text-primary underline underline-offset-4"
            >
              <FileText aria-hidden className="w-4 h-4" /> Ouvrir le PDF dans un nouvel onglet
            </a>
          ) : (
            <img
              src={documentPreview.url}
              alt={`${DOC_TYPE_LABEL[item.docType]} de ${item.artisanFullName}`}
              className="max-h-80 w-auto mx-auto rounded-field"
            />
          )
        ) : (
          <Button
            variant="outline"
            size="sm"
            isLoading={isLoadingPreview}
            onClick={() => void preview.load(item.id)}
            leadingIcon={<Eye aria-hidden className="w-4 h-4" />}
          >
            {isLoadingPreview ? 'Chargement...' : 'Afficher le document'}
          </Button>
        )}
        {preview.error && (
          <p role="alert" className="text-sm text-destructive mt-2">
            {preview.error}
          </p>
        )}
      </div>

      {review.error && (
        <p role="alert" className="text-sm text-destructive">
          {review.error}
        </p>
      )}

      {isRejecting ? (
        <div className="space-y-3 pt-3 border-t border-border-faint">
          <TextAreaField
            id={`reject-note-${item.id}`}
            label="Motif du rejet (visible par l’artisan)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            minLength={MIN_NOTE_LENGTH}
            maxLength={1000}
            placeholder="Ex. : photo illisible, merci de renvoyer un scan net."
            hint={`${MIN_NOTE_LENGTH} caractères minimum.`}
          />
          <div className="flex gap-3">
            <Button
              variant="ghost"
              className="flex-1"
              onClick={() => {
                setIsRejecting(false);
                setNote('');
              }}
            >
              Annuler
            </Button>
            <Button
              variant="danger"
              className="flex-1"
              disabled={!isNoteValid}
              isLoading={isSubmittingReject}
              onClick={() => void handleConfirmReject()}
            >
              {isSubmittingReject ? 'Envoi...' : 'Confirmer le rejet'}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-3 pt-3 border-t border-border-faint">
          <Button
            variant="danger-outline"
            className="flex-1"
            disabled={isBusy}
            onClick={() => setIsRejecting(true)}
          >
            Rejeter
          </Button>
          <Button
            variant="brand"
            className="flex-1"
            disabled={isBusy && !isApproving}
            isLoading={isApproving}
            onClick={() => void review.approve(item.id)}
          >
            {isApproving ? 'Envoi...' : 'Approuver'}
          </Button>
        </div>
      )}
    </Card>
  );
};

/**
 * Espace admin de revue des artisans (BUILD_PLAN.md, espace admin) : outil
 * interne, sobre — priorité à la lisibilité et à la sûreté d'usage.
 * En-tête CLAIR et neutre, volontairement distinct du bandeau vert de
 * l'espace Pro : aucune confusion possible entre les deux espaces.
 * Hors de MainLayout (RequireAdminRoute le monte sous MinimalLayout) et
 * sans aucun lien vers cet espace ailleurs dans l'app (URL directe seule).
 */
export const AdminVerificationQueueScreen: React.FC = () => {
  const auth = useAuth();
  const queue = useAdminVerificationQueue();
  const pendingCount = queue.data?.length ?? null;

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 bg-surface shadow-card">
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-3 h-16 px-4 md:px-8">
          <div className="flex items-center gap-2">
            <Logo />
            <span className="inline-flex items-center gap-1 rounded-md bg-foreground px-1.5 py-0.5 text-caption font-bold uppercase tracking-wider text-white">
              <ShieldCheck aria-hidden className="w-3.5 h-3.5" />
              Admin
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void auth.logout()}
            leadingIcon={<LogOut aria-hidden className="w-4 h-4" />}
          >
            Déconnexion
          </Button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 md:px-8 pt-6 pb-16 space-y-5">
        <div className="space-y-1">
          <h1 className="font-display text-display-md font-semibold text-primary">
            Documents à vérifier
          </h1>
          <p className="text-sm text-muted-foreground">
            {pendingCount == null
              ? 'File d’attente des documents envoyés par les artisans.'
              : `${pendingCount} document${pendingCount > 1 ? 's' : ''} en attente, du plus ancien au plus récent.`}
          </p>
        </div>

        {queue.isLoading && !queue.data ? (
          <div className="space-y-4" aria-busy="true">
            <Skeleton className="h-44 rounded-card" />
            <Skeleton className="h-44 rounded-card" />
          </div>
        ) : queue.error && !queue.data ? (
          <ErrorState message={queue.error.message} onRetry={queue.reload} />
        ) : queue.data && queue.data.length === 0 ? (
          <EmptyState
            icon={<ShieldCheck />}
            title="Aucun document en attente de revue."
            description="Les nouveaux envois des artisans apparaîtront ici."
          />
        ) : (
          <ul className="space-y-4">
            {queue.data?.map((item) => (
              <li key={item.id}>
                <VerificationCard item={item} onReviewed={queue.removeFromQueue} />
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
};
