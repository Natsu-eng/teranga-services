import React, { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown, MapPin } from 'lucide-react';
import { usePlace } from '../../features/location/usePlace';
import { cn } from '../../lib/cn';
import { NEIGHBORHOODS, neighborhoodPlace } from '../../lib/places';

/**
 * Sélecteur de quartier de l'en-tête client, en « disclosure » accessible :
 * `aria-expanded` sur le déclencheur, fermeture par Échap (le focus revient
 * au déclencheur) ou par un clic à l'extérieur, quartier courant signalé
 * par `aria-current` et non par la seule couleur.
 *
 * Le quartier choisi est le LIEU D'INTERVENTION partagé (PlaceProvider),
 * avec ses vraies coordonnées : c'est lui que l'écran de demande propose
 * par défaut. En-tête et demande ne peuvent plus se contredire.
 */
export const LocationPicker: React.FC = () => {
  const { place, setPlace } = usePlace();
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
        <span className="font-medium truncate max-w-[12rem]">{place.label}</span>
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
            {NEIGHBORHOODS.map((neighborhood) => {
              const isSelected =
                place.kind === 'quartier' && place.neighborhoodId === neighborhood.id;
              return (
                <li key={neighborhood.id}>
                  <button
                    ref={isSelected ? selectedRef : undefined}
                    type="button"
                    aria-current={isSelected ? 'true' : undefined}
                    onClick={() => {
                      setPlace(neighborhoodPlace(neighborhood.id));
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
                    <span>{neighborhood.label}</span>
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
