import { cn } from '../../lib/cn';

/*
 * Classes partagées des composants cœur, exposées à part pour pouvoir
 * habiller un <Link> (react-router) exactement comme un bouton, une carte ou
 * une pastille — sans dupliquer les chaînes de classes dans les écrans.
 * Fichier sans composant : la règle react-refresh « un fichier = des
 * composants » reste respectée côté .tsx.
 */

// ---------------------------------------------------------------- Bouton

/**
 * - primary        : action principale de l'écran, OR (texte vert profond,
 *                    contraste 5,6:1). Une seule par écran.
 * - brand          : action de marque pleine (émeraude, texte blanc 8,2:1).
 * - outline        : action secondaire, contour émeraude doux.
 * - ghost          : action tertiaire, sans fond.
 * - danger         : action destructive confirmée (fond rouge).
 * - danger-outline : action destructive de premier niveau (contour rouge).
 * - danger-ghost   : action destructive discrète, sans fond (déconnexion).
 * - on-dark        : action posée sur un bandeau vert profond (espace Pro).
 */
export type ButtonVariant =
  | 'primary'
  | 'brand'
  | 'outline'
  | 'ghost'
  | 'danger'
  | 'danger-outline'
  | 'danger-ghost'
  | 'on-dark';

export type ButtonSize = 'sm' | 'md' | 'lg';

const BUTTON_BASE =
  'inline-flex items-center justify-center gap-2 rounded-full font-semibold select-none cursor-pointer text-center ' +
  'transition-[background-color,color,box-shadow,transform] duration-150 motion-safe:active:scale-[0.98] ' +
  'disabled:cursor-not-allowed disabled:opacity-55 disabled:active:scale-100';

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-primary shadow-cta hover:bg-accent-alt',
  brand: 'bg-primary-emerald text-white hover:bg-primary',
  outline:
    'bg-surface text-primary ring-1 ring-inset ring-primary-emerald/40 hover:bg-emerald-tint',
  ghost: 'text-primary hover:bg-emerald-tint',
  danger: 'bg-destructive text-white hover:bg-destructive/90',
  'danger-outline':
    'bg-surface text-destructive ring-1 ring-inset ring-destructive/45 hover:bg-destructive-soft',
  'danger-ghost': 'text-destructive hover:bg-destructive-soft',
  'on-dark': 'bg-white/10 text-white ring-1 ring-inset ring-white/30 hover:bg-white/20',
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'min-h-9 px-4 py-1.5 text-sm',
  md: 'min-h-11 px-5 py-2 text-sm',
  lg: 'min-h-14 px-6 py-3 text-base',
};

export interface ButtonStyleOptions {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  className?: string;
}

export function buttonClasses({
  variant = 'brand',
  size = 'md',
  fullWidth = false,
  className,
}: ButtonStyleOptions = {}): string {
  return cn(
    BUTTON_BASE,
    BUTTON_VARIANTS[variant],
    BUTTON_SIZES[size],
    fullWidth && 'w-full',
    className,
  );
}

// ---------------------------------------------------------------- Carte

/**
 * - default : surface blanche, ombre diffuse, aucun bord dur.
 * - tint    : vert très clair (zones IA, encarts d'information), sans ombre.
 * Les tonalités claires n'imposent pas de couleur de texte (héritée) : une
 * couleur passée en `className` s'applique alors sans conflit.
 * - dark    : vert profond (résultat IA, cartes Pro) — poser data-tone="dark".
 */
export type CardTone = 'default' | 'tint' | 'dark';
export type CardPadding = 'none' | 'sm' | 'md' | 'lg';

const CARD_TONES: Record<CardTone, string> = {
  default: 'bg-surface shadow-card',
  tint: 'bg-emerald-tint',
  dark: 'bg-primary text-white shadow-card',
};

const CARD_PADDINGS: Record<CardPadding, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-5 md:p-6',
};

export interface CardStyleOptions {
  tone?: CardTone;
  padding?: CardPadding;
  /** Carte cliquable : élévation au survol (le déplacement est coupé en reduced-motion). */
  interactive?: boolean;
  className?: string;
}

export function cardClasses({
  tone = 'default',
  padding = 'md',
  interactive = false,
  className,
}: CardStyleOptions = {}): string {
  return cn(
    'block rounded-card',
    CARD_TONES[tone],
    CARD_PADDINGS[padding],
    interactive &&
      'cursor-pointer transition-[box-shadow,transform] duration-200 hover:shadow-card-hover motion-safe:hover:-translate-y-0.5',
    className,
  );
}

// ---------------------------------------------------------------- Pastille de filtre

export function chipClasses(selected: boolean, className?: string): string {
  return cn(
    'inline-flex shrink-0 items-center gap-1.5 h-9 px-4 rounded-full text-sm font-medium whitespace-nowrap cursor-pointer transition-colors duration-150',
    selected
      ? 'bg-primary text-white shadow-sm'
      : 'bg-surface text-muted-foreground shadow-card hover:bg-emerald-tint hover:text-primary',
    className,
  );
}

// ---------------------------------------------------------------- Champ de formulaire

/**
 * Contour #707972 (muted-foreground-soft) : contraste 4,6:1 avec le blanc,
 * au-dessus du minimum de 3:1 exigé pour délimiter un champ (WCAG 1.4.11).
 * Focus : anneau émeraude de 2 px (le contour natif est remplacé, jamais
 * supprimé sans équivalent visible).
 */
export function fieldClasses(
  options: { invalid?: boolean; multiline?: boolean; className?: string } = {},
): string {
  const { invalid = false, multiline = false, className } = options;
  return cn(
    'w-full rounded-field bg-surface px-4 text-base text-foreground placeholder:text-muted-foreground-soft',
    'ring-1 ring-inset transition-shadow duration-150 focus:outline-none focus:ring-2',
    invalid
      ? 'ring-destructive focus:ring-destructive'
      : 'ring-muted-foreground-soft focus:ring-primary-emerald',
    'disabled:cursor-not-allowed disabled:bg-surface-muted disabled:opacity-70',
    multiline ? 'py-3 min-h-28 resize-none leading-relaxed' : 'h-12',
    className,
  );
}
