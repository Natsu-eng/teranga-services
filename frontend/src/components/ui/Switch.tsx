import React from 'react';
import { cn } from '../../lib/cn';

interface SwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Nom accessible obligatoire (le libellé visible est souvent à côté). */
  label: string;
  disabled?: boolean;
  /** `on-dark` : posé sur le bandeau vert profond de l'espace Pro. */
  tone?: 'light' | 'on-dark';
}

/**
 * Interrupteur on/off (`role="switch"`, état dans `aria-checked`).
 * Activé : curseur vert profond sur piste émeraude claire (lisible sur fond
 * clair comme sur le bandeau Pro) ; l'état se lit aussi par la position du
 * curseur, pas seulement par la couleur.
 */
export const Switch: React.FC<SwitchProps> = ({
  checked,
  onChange,
  label,
  disabled,
  tone = 'light',
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    disabled={disabled}
    onClick={() => onChange(!checked)}
    className={cn(
      'relative inline-flex shrink-0 w-14 h-8 rounded-full cursor-pointer transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-60',
      checked
        ? 'bg-primary-emerald-foreground'
        : tone === 'on-dark'
          ? 'bg-white/25'
          : 'bg-border-strong',
    )}
  >
    <span
      aria-hidden
      className={cn(
        'absolute top-1 left-1 w-6 h-6 rounded-full shadow transition-transform duration-200',
        checked ? 'translate-x-6 bg-primary' : 'translate-x-0 bg-white',
      )}
    />
  </button>
);
