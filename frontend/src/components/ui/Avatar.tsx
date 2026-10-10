import React, { useState } from 'react';
import { UserRound } from 'lucide-react';
import { cn } from '../../lib/cn';
import { hasRealName } from '../../lib/identity';
import { initialsFrom } from '../../lib/initials';
import { SafeImage } from './SafeImage';

export type AvatarSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

interface AvatarProps {
  name: string;
  src?: string | null;
  size?: AvatarSize;
  /** `rounded` : carré arrondi (cartes artisan) · `circle` : rond (avis, profil). */
  shape?: 'circle' | 'rounded';
  /**
   * Décoratif quand le nom est déjà écrit à côté (carte, avis) : l'image est
   * alors ignorée par les lecteurs d'écran au lieu de répéter le nom.
   */
  decorative?: boolean;
  className?: string;
}

const SIZES: Record<AvatarSize, string> = {
  xs: 'w-8 h-8 text-xs',
  sm: 'w-10 h-10 text-sm',
  md: 'w-14 h-14 text-base',
  lg: 'w-18 h-18 text-xl',
  xl: 'w-28 h-28 text-display-md',
};

/*
 * Couleurs des initiales, toutes issues des tokens et toutes au-dessus de
 * 4,5:1 de contraste texte/fond. Le choix est déterministe (dérivé du nom) :
 * une même personne garde la même couleur sur tous les écrans.
 */
const INITIALS_TONES = [
  'bg-emerald-tint text-primary',
  'bg-accent-soft text-accent-foreground-strong',
  'bg-success text-success-foreground',
  'bg-primary text-primary-emerald-foreground',
  'bg-surface-muted text-primary-emerald',
] as const;

function avatarToneIndex(name: string): number {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return hash % INITIALS_TONES.length;
}

/**
 * Avatar d'une personne : photo réelle (chargée via SafeImage, en lazy) ou,
 * à défaut — pas de photo, URL cassée —, initiales colorées. Jamais une
 * silhouette générique quand on connaît le nom.
 */
export const Avatar: React.FC<AvatarProps> = ({
  name,
  src,
  size = 'md',
  shape = 'circle',
  decorative = false,
  className,
}) => {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const showImage = Boolean(src) && src !== failedSrc;
  // Compte hérité dont le « nom » est resté son numéro : jamais de numéro
  // lu à voix haute ni de « + » en guise d'initiales (lib/identity.ts).
  const knownName = hasRealName(name);
  const label = knownName ? name : 'Membre Téranga';
  const radius = shape === 'circle' ? 'rounded-full' : 'rounded-2xl';

  if (showImage) {
    return (
      <SafeImage
        src={src}
        fallback="/images/placeholder-avatar.svg"
        alt={decorative ? '' : label}
        // Une URL qui échoue bascule sur les initiales (plus parlantes
        // qu'une silhouette), et seulement pour CETTE URL : une nouvelle
        // photo est retentée normalement.
        onError={() => setFailedSrc(src ?? null)}
        className={cn('shrink-0 object-cover bg-surface-muted', SIZES[size], radius, className)}
      />
    );
  }

  return (
    <span
      {...(decorative ? { 'aria-hidden': true } : { role: 'img', 'aria-label': label })}
      className={cn(
        'shrink-0 inline-flex items-center justify-center font-display font-semibold select-none',
        INITIALS_TONES[avatarToneIndex(name)],
        SIZES[size],
        radius,
        className,
      )}
    >
      {knownName ? initialsFrom(name) : <UserRound aria-hidden className="w-[55%] h-[55%]" />}
    </span>
  );
};
