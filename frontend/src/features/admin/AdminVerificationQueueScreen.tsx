import React, { useState } from 'react';
import { FileText, LogOut, ShieldCheck } from 'lucide-react';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
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

  async function handleConfirmReject(): Promise<void> {
    if (note.trim().length < 3) return;
    const result = await review.reject(item.id, note.trim());
    if (result) {
      setIsRejecting(false);
      setNote('');
    }
  }

  return (
    <div className="bg-white rounded-2xl p-5 border border-border-subtle space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-sora text-sm font-bold text-foreground">{item.artisanFullName}</p>
          <p className="text-xs text-muted-foreground-soft">
            {DOC_TYPE_LABEL[item.docType]} · déposé le {formatDateTime(item.createdAt)}
          </p>
        </div>
      </div>

      <div>
        {documentPreview ? (
          documentPreview.isPdf ? (
            <a
              href={documentPreview.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 text-sm font-sora font-bold text-primary underline"
            >
              <FileText className="w-4 h-4" /> Ouvrir le PDF dans un nouvel onglet
            </a>
          ) : (
            <img
              src={documentPreview.url}
              alt={`${DOC_TYPE_LABEL[item.docType]} de ${item.artisanFullName}`}
              className="max-h-80 w-auto rounded-xl border border-border-subtle"
            />
          )
        ) : (
          <button
            type="button"
            onClick={() => void preview.load(item.id)}
            disabled={isLoadingPreview}
            className="inline-flex items-center gap-2 py-2 px-4 rounded-full border-1.5 border-primary text-primary font-sora text-xs font-bold hover:bg-primary/5 active:scale-95 transition-all cursor-pointer disabled:opacity-60"
          >
            {isLoadingPreview ? 'Chargement...' : 'Afficher le document'}
          </button>
        )}
        {preview.error && <p className="text-xs text-destructive mt-2">{preview.error}</p>}
      </div>

      {review.error && <p className="text-xs text-destructive">{review.error}</p>}

      {isRejecting ? (
        <div className="space-y-2 pt-2 border-t border-border-faint">
          <label
            htmlFor={`reject-note-${item.id}`}
            className="text-xs font-sora font-bold text-muted-foreground-soft uppercase"
          >
            Motif du rejet (visible par l’artisan)
          </label>
          <textarea
            id={`reject-note-${item.id}`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            minLength={3}
            maxLength={1000}
            placeholder="Ex. : photo illisible, merci de renvoyer un scan net."
            className="w-full p-3 rounded-xl border border-border-strong focus:border-destructive focus:ring-1 focus:ring-destructive text-sm outline-none resize-none"
          />
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => {
                setIsRejecting(false);
                setNote('');
              }}
              className="flex-1 py-2.5 rounded-full border border-border-strong text-muted-foreground font-sora text-xs font-bold hover:bg-surface-muted transition-all cursor-pointer"
            >
              Annuler
            </button>
            <button
              type="button"
              onClick={() => void handleConfirmReject()}
              disabled={note.trim().length < 3 || isSubmittingReject}
              className="flex-1 py-2.5 rounded-full bg-destructive text-white font-sora text-xs font-bold hover:opacity-90 active:scale-95 transition-all cursor-pointer disabled:opacity-60"
            >
              {isSubmittingReject ? 'Envoi...' : 'Confirmer le rejet'}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-3 pt-2 border-t border-border-faint">
          <button
            type="button"
            onClick={() => setIsRejecting(true)}
            disabled={isBusy}
            className="flex-1 py-2.5 rounded-full border border-destructive text-destructive font-sora text-xs font-bold hover:bg-destructive-soft transition-all cursor-pointer disabled:opacity-60"
          >
            Rejeter
          </button>
          <button
            type="button"
            onClick={() => void review.approve(item.id)}
            disabled={isBusy}
            className="flex-1 py-2.5 rounded-full bg-primary text-white font-sora text-xs font-bold hover:opacity-90 active:scale-95 transition-all cursor-pointer disabled:opacity-60"
          >
            {isApproving ? 'Envoi...' : 'Approuver'}
          </button>
        </div>
      )}
    </div>
  );
};

/**
 * Espace admin de revue des artisans (BUILD_PLAN.md, espace admin) : outil
 * interne, priorité à la lisibilité et à la sûreté d'usage sur
 * l'esthétique. Volontairement en dehors de `MainLayout`
 * (`RequireAdminRoute` monte cet écran sous `MinimalLayout`, App.tsx) : pas
 * de Header ni de BottomNav orientés client/artisan qui n'auraient aucun
 * sens ici, et surtout aucun lien de navigation visible vers cet espace
 * ailleurs dans l'app (accès uniquement par URL directe).
 */
export const AdminVerificationQueueScreen: React.FC = () => {
  const auth = useAuth();
  const queue = useAdminVerificationQueue();

  return (
    <main className="min-h-screen bg-background pb-16">
      <header className="bg-primary text-white px-4 md:px-8 pt-8 pb-6">
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-white/15 flex items-center justify-center shrink-0">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <p className="font-sora text-xs uppercase tracking-wider text-primary-emerald-foreground">
                Espace Admin
              </p>
              <h1 className="font-headline-md text-xl font-bold">Documents à vérifier</h1>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void auth.logout()}
            className="flex items-center gap-2 py-2 px-3 rounded-full border border-white/30 text-white font-sora text-xs font-bold hover:bg-white/10 transition-all cursor-pointer shrink-0"
          >
            <LogOut className="w-4 h-4" />
            Déconnexion
          </button>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-4 md:px-8 pt-6 space-y-4">
        {queue.isLoading && !queue.data ? (
          <div className="space-y-4">
            <Skeleton className="h-40 rounded-2xl" />
            <Skeleton className="h-40 rounded-2xl" />
          </div>
        ) : queue.error && !queue.data ? (
          <ErrorState message={queue.error.message} onRetry={queue.reload} />
        ) : queue.data && queue.data.length === 0 ? (
          <EmptyState title="Aucun document en attente de revue." />
        ) : (
          queue.data?.map((item) => (
            <VerificationCard key={item.id} item={item} onReviewed={queue.removeFromQueue} />
          ))
        )}
      </div>
    </main>
  );
};
