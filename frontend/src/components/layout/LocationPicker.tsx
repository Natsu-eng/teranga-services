import React, { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown, MapPin } from 'lucide-react';
import { cn } from '../../lib/cn';

/** Quartiers proposés (affichage uniquement : la recherche se fait par position réelle). */
const LOCATIONS = [
  'Dakar Plateau',
  'Almadies, Dakar',
  'Ouakam, Dakar',
  'Mermoz - Sacré Cœur',
  'Yoff - Ngor',
  'Point E, Dakar',
] as const;

interface LocationPickerProps {
  location: string;
  setLocation: (location: string) => void;
}

/**
 * Sélecteur de quartier de l'en-tête client, en « disclosure » accessible :
 * `aria-expanded` sur le déclencheur, fermeture par Échap (le focus revient
 * au déclencheur) ou par un clic à l'extérieur, quartier courant signalé
 * par `aria-current` et non par la seule couleur.
 */
export const LocationPicker: React.FC<LocationPickerProps> = ({ location, setLocation }) => {
  const [isOpen, setIsOpen] = useState(false);
  const panelId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selectedRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    // Le quartier courant reçoit le focus à l'ouverture (navigation clavier directe).
    selectedRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    };
    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('pointerdown', handlePointerDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={() => setIsOpen((open) => !open)}
        className="-ml-1 inline-flex items-center gap-1 rounded-full px-1 py-0.5 text-sm text-muted-foreground hover:text-primary cursor-pointer transition-colors"
      >
        <MapPin aria-hidden className="w-4 h-4 text-primary-emerald" />
        <span className="sr-only">Quartier : </span>
        <span className="font-medium truncate max-w-[12rem]">{location}</span>
        <ChevronDown
          aria-hidden
          className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')}
        />
      </button>

      {isOpen && (
        <div
          id={panelId}
          className="absolute top-full left-0 mt-2 w-64 max-w-[calc(100vw-2rem)] bg-surface rounded-card shadow-card-hover p-2 z-50"
        >
          <p className="px-3 py-1.5 text-caption font-semibold uppercase tracking-wider text-muted-foreground">
            Quartier à Dakar
          </p>
          <ul>
            {LOCATIONS.map((loc) => {
              const isSelected = loc === location;
              return (
                <li key={loc}>
                  <button
                    ref={isSelected ? selectedRef : undefined}
                    type="button"
                    aria-current={isSelected ? 'true' : undefined}
                    onClick={() => {
                      setLocation(loc);
                      setIsOpen(false);
                      triggerRef.current?.focus();
                    }}
                    className={cn(
                      'w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-field text-left text-sm cursor-pointer transition-colors',
                      isSelected
                        ? 'bg-emerald-tint text-primary font-semibold'
                        : 'text-foreground hover:bg-surface-muted',
                    )}
                  >
                    <span>{loc}</span>
                    {isSelected && <Check aria-hidden className="w-4 h-4" />}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
};
