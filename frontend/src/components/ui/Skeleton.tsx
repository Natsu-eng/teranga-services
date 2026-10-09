import React from 'react';
import { cn } from '../../lib/cn';

interface SkeletonProps {
  className?: string;
}

/**
 * Bloc de chargement à la forme du contenu attendu (évite les sauts de mise
 * en page). Purement visuel : masqué des lecteurs d'écran, l'écran annonce
 * le chargement autrement. La pulsation est coupée en reduced-motion.
 */
export const Skeleton: React.FC<SkeletonProps> = ({ className }) => (
  <div aria-hidden className={cn('animate-pulse rounded-field bg-border-subtle', className)} />
);
