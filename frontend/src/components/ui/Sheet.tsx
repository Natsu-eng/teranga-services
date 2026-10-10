import React, { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { IconButton } from './IconButton';

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
}

/** Éléments atteignables au clavier, pour le piège de focus. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Panneau modal : glisse du bas sur mobile, centré sur grand écran.
 *
 * Accessibilité d'une vraie fenêtre modale :
 * - `role="dialog"` + `aria-modal`, titre relié par `aria-labelledby` ;
 * - le focus entre dans le panneau à l'ouverture, y reste (Tab / Maj+Tab
 *   bouclent) et revient sur l'élément d'origine à la fermeture ;
 * - Échap, la croix ou un clic sur le voile ferment ;
 * - le défilement de la page est bloqué pendant l'ouverture.
 * Le contenu n'est monté qu'à l'ouverture : aucun appel réseau tant que
 * l'utilisateur n'a rien demandé.
 */
export const Sheet: React.FC<SheetProps> = ({ open, onClose, title, description, children }) => {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  // Garde la dernière version du rappel sans relancer l'effet d'ouverture.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const panel = panelRef.current;
    const first = panel?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel)?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !panel) return;
      const focusables = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (focusables.length === 0) return;
      const firstEl = focusables[0];
      const lastEl = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === firstEl) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && document.activeElement === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center">
      <div aria-hidden className="absolute inset-0 bg-foreground/45" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className="relative w-full md:max-w-lg max-h-[88vh] overflow-y-auto bg-surface rounded-t-sheet md:rounded-sheet shadow-card-hover px-5 pt-3 pb-safe focus:outline-none"
      >
        {/* Poignée visuelle (mobile) : signale un panneau qui se ferme. */}
        <div
          aria-hidden
          className="mx-auto mb-2 h-1.5 w-10 rounded-full bg-border-strong md:hidden"
        />
        <div className="flex items-start justify-between gap-3 pb-4">
          <div className="space-y-1 pt-1">
            <h2 id={titleId} className="font-display text-display-sm font-semibold text-primary">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="text-sm text-muted-foreground">
                {description}
              </p>
            )}
          </div>
          <IconButton label="Fermer" onClick={onClose} className="-mr-2">
            <X aria-hidden className="w-5 h-5" />
          </IconButton>
        </div>
        <div className="pb-6">{children}</div>
      </div>
    </div>,
    document.body,
  );
};
