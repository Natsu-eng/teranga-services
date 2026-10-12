import React, { useState } from 'react';
import { Button } from '../../../components/ui/Button';
import { TextAreaField } from '../../../components/ui/Field';
import { Sheet } from '../../../components/ui/Sheet';
import { ApiError } from '../../../lib/api';

interface ConfirmActionSheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Conséquences exactes de l'action, dites AVANT de confirmer. */
  effect: React.ReactNode;
  confirmLabel: string;
  tone?: 'brand' | 'danger';
  /** Motif : `required` exige `minLength` caractères ; `optional` l'accepte vide. */
  reason: { label: string; hint?: string; mode: 'required' | 'optional'; minLength?: number };
  /** L'action ; une erreur serveur est affichée telle quelle dans la feuille. */
  onConfirm: (reason: string) => Promise<void>;
}

/**
 * Confirmation d'une action admin sensible : l'effet est énoncé, le motif
 * saisi, puis l'action part. Le bouton reste inactif tant qu'un motif
 * obligatoire est trop court ; le serveur revérifie de toute façon et son
 * refus (dernier admin, avis déjà masqué...) s'affiche ici, en clair.
 */
export const ConfirmActionSheet: React.FC<ConfirmActionSheetProps> = ({
  open,
  onClose,
  title,
  effect,
  confirmLabel,
  tone = 'brand',
  reason,
  onConfirm,
}) => {
  const [text, setText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const minLength = reason.mode === 'required' ? (reason.minLength ?? 1) : 0;
  const tooShort = text.trim().length < minLength;

  const close = () => {
    if (isSubmitting) return;
    setText('');
    setError(null);
    onClose();
  };

  const submit = async () => {
    if (tooShort) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await onConfirm(text.trim());
      setText('');
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action impossible. Réessayez.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Sheet open={open} onClose={close} title={title}>
      <div className="space-y-4">
        <div className="text-sm text-foreground">{effect}</div>
        <TextAreaField
          label={reason.label}
          hint={
            reason.hint ??
            (reason.mode === 'required'
              ? `${minLength} caractères minimum. Inscrit au journal d’audit.`
              : 'Facultatif. Inscrit au journal d’audit.')
          }
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={3}
          maxLength={1000}
        />
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Button
            variant={tone === 'danger' ? 'danger' : 'brand'}
            className="flex-1"
            isLoading={isSubmitting}
            disabled={tooShort}
            onClick={submit}
          >
            {confirmLabel}
          </Button>
          <Button variant="ghost" disabled={isSubmitting} onClick={close}>
            Annuler
          </Button>
        </div>
      </div>
    </Sheet>
  );
};
