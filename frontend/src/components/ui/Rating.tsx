import React from 'react';
import { Star } from 'lucide-react';
import { cn } from '../../lib/cn';

/** Note au format français : 4.8 -> « 4,8 ». */
function formatRating(value: number): string {
  return value.toFixed(1).replace('.', ',');
}

function reviewsLabel(count: number): string {
  return `${count} avis`;
}

interface RatingProps {
  /** Note moyenne sur 5. Ignorée tant qu'il n'existe aucun avis (`count === 0`). */
  value: number | null;
  count: number;
  size?: 'sm' | 'md' | 'lg';
  /** Masque « (12 avis) » quand le nombre est déjà affiché ailleurs. */
  hideCount?: boolean;
  /** `on-dark` : sur fond vert profond. */
  tone?: 'default' | 'on-dark';
  className?: string;
}

const SIZES = {
  sm: { text: 'text-sm', icon: 'w-4 h-4' },
  md: { text: 'text-base', icon: 'w-[18px] h-[18px]' },
  lg: { text: 'text-lg', icon: 'w-5 h-5' },
} as const;

/**
 * Note moyenne : étoile or + valeur + nombre d'avis.
 *
 * Honnêteté avant tout : un artisan sans aucun avis affiche « Nouveau »,
 * jamais « 0,0 » (qui se lirait comme une mauvaise note) ni une note
 * inventée. L'étoile est décorative : le sens est porté par le texte et
 * par un libellé complet pour les lecteurs d'écran.
 */
export const Rating: React.FC<RatingProps> = ({
  value,
  count,
  size = 'sm',
  hideCount = false,
  tone = 'default',
  className,
}) => {
  const s = SIZES[size];
  const muted = tone === 'on-dark' ? 'text-primary-emerald-foreground' : 'text-muted-foreground';

  if (count === 0 || value == null) {
    return (
      <span
        className={cn(
          'inline-flex items-center rounded-full px-2.5 h-6 text-caption font-semibold uppercase tracking-wide',
          tone === 'on-dark'
            ? 'bg-white/10 text-white'
            : 'bg-accent-soft text-accent-foreground-strong',
          className,
        )}
      >
        Nouveau
      </span>
    );
  }

  return (
    <span className={cn('inline-flex items-center gap-1', s.text, className)}>
      <span className="sr-only">
        Note de {formatRating(value)} sur 5, {reviewsLabel(count)}
      </span>
      <Star aria-hidden className={cn(s.icon, 'text-accent')} fill="currentColor" strokeWidth={0} />
      <span
        aria-hidden
        className={cn('font-bold', tone === 'on-dark' ? 'text-white' : 'text-foreground')}
      >
        {formatRating(value)}
      </span>
      {!hideCount && (
        <span aria-hidden className={muted}>
          ({reviewsLabel(count)})
        </span>
      )}
    </span>
  );
};

interface StarRowProps {
  /** Nombre d'étoiles pleines, de 0 à 5. */
  value: number;
  size?: 'sm' | 'md';
  className?: string;
}

/** Rangée de 5 étoiles en lecture seule (note d'un avis individuel). */
export const StarRow: React.FC<StarRowProps> = ({ value, size = 'sm', className }) => (
  <span className={cn('inline-flex items-center gap-0.5', className)}>
    <span className="sr-only">Note : {value} sur 5</span>
    {[1, 2, 3, 4, 5].map((n) => (
      <Star
        key={n}
        aria-hidden
        className={cn(
          size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4',
          n <= value ? 'text-accent' : 'text-border-strong',
        )}
        fill="currentColor"
        strokeWidth={0}
      />
    ))}
  </span>
);

interface RatingInputProps {
  value: number;
  onChange: (value: number) => void;
  /** Nom du groupe, lu par les lecteurs d'écran. */
  label?: string;
  disabled?: boolean;
}

/**
 * Saisie d'une note de 1 à 5 étoiles (dépôt d'un avis). Chaque étoile est
 * un vrai bouton nommé (« 3 étoiles ») et l'état choisi est exposé par
 * `aria-pressed` : utilisable au clavier comme au lecteur d'écran.
 */
export const RatingInput: React.FC<RatingInputProps> = ({
  value,
  onChange,
  label = 'Votre note',
  disabled = false,
}) => (
  <div role="group" aria-label={label} className="flex items-center gap-1">
    {[1, 2, 3, 4, 5].map((n) => (
      <button
        key={n}
        type="button"
        disabled={disabled}
        onClick={() => onChange(n)}
        aria-label={`${n} étoile${n > 1 ? 's' : ''}`}
        aria-pressed={n === value}
        className="w-11 h-11 -mx-1 inline-flex items-center justify-center rounded-full cursor-pointer hover:bg-accent-soft/60 transition-colors disabled:cursor-not-allowed"
      >
        <Star
          aria-hidden
          className={cn('w-7 h-7', n <= value ? 'text-accent' : 'text-border-strong')}
          fill="currentColor"
          strokeWidth={0}
        />
      </button>
    ))}
  </div>
);
