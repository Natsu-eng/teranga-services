import React, { useId } from 'react';
import { cn } from '../../lib/cn';
import { fieldClasses } from './styles';

interface FieldShellProps {
  id: string;
  label: string;
  /** Libellé masqué visuellement mais toujours lu (champ déjà explicité par son contexte). */
  hideLabel?: boolean;
  hint?: React.ReactNode;
  error?: string | null;
  hintId: string;
  errorId: string;
  className?: string;
  children: React.ReactNode;
}

/**
 * Habillage commun : libellé réellement associé au champ (`htmlFor`),
 * aide et erreur reliées par `aria-describedby`. L'erreur est annoncée
 * immédiatement (`role="alert"`).
 */
const FieldShell: React.FC<FieldShellProps> = ({
  id,
  label,
  hideLabel,
  hint,
  error,
  hintId,
  errorId,
  className,
  children,
}) => (
  <div className={cn('space-y-1.5', className)}>
    <label
      htmlFor={id}
      className={hideLabel ? 'sr-only' : 'block text-sm font-semibold text-foreground'}
    >
      {label}
    </label>
    {children}
    {hint && !error && (
      <p id={hintId} className="text-xs text-muted-foreground">
        {hint}
      </p>
    )}
    {error && (
      <p id={errorId} role="alert" className="text-sm text-destructive">
        {error}
      </p>
    )}
  </div>
);

interface CommonFieldProps {
  label: string;
  hideLabel?: boolean;
  hint?: React.ReactNode;
  error?: string | null;
  /** Classes du conteneur (mise en page), pas du champ lui-même. */
  className?: string;
  /** Classes supplémentaires appliquées au champ (ex. texte centré du code OTP). */
  inputClassName?: string;
}

function useFieldIds(explicitId: string | undefined) {
  const generated = useId();
  const id = explicitId ?? generated;
  return { id, hintId: `${id}-aide`, errorId: `${id}-erreur` };
}

function describedBy(
  hint: React.ReactNode,
  error: string | null | undefined,
  ids: { hintId: string; errorId: string },
): string | undefined {
  if (error) return ids.errorId;
  if (hint) return ids.hintId;
  return undefined;
}

export type TextFieldProps = CommonFieldProps &
  Omit<React.ComponentPropsWithRef<'input'>, 'className'>;

/** Champ texte (texte, téléphone, nombre, URL...) avec libellé obligatoire. */
export const TextField: React.FC<TextFieldProps> = ({
  label,
  hideLabel,
  hint,
  error,
  className,
  inputClassName,
  id: explicitId,
  ...props
}) => {
  const ids = useFieldIds(explicitId);
  return (
    <FieldShell
      {...ids}
      label={label}
      hideLabel={hideLabel}
      hint={hint}
      error={error}
      className={className}
    >
      <input
        {...props}
        id={ids.id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint, error, ids)}
        className={fieldClasses({ invalid: Boolean(error), className: inputClassName })}
      />
    </FieldShell>
  );
};

export type TextAreaFieldProps = CommonFieldProps &
  Omit<React.ComponentPropsWithRef<'textarea'>, 'className'>;

/** Zone de texte multiligne avec libellé obligatoire. */
export const TextAreaField: React.FC<TextAreaFieldProps> = ({
  label,
  hideLabel,
  hint,
  error,
  className,
  inputClassName,
  id: explicitId,
  ...props
}) => {
  const ids = useFieldIds(explicitId);
  return (
    <FieldShell
      {...ids}
      label={label}
      hideLabel={hideLabel}
      hint={hint}
      error={error}
      className={className}
    >
      <textarea
        {...props}
        id={ids.id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint, error, ids)}
        className={fieldClasses({
          invalid: Boolean(error),
          multiline: true,
          className: inputClassName,
        })}
      />
    </FieldShell>
  );
};

export type SelectFieldProps = CommonFieldProps &
  Omit<React.ComponentPropsWithRef<'select'>, 'className'>;

/** Liste déroulante native (accessible et adaptée au mobile) avec libellé obligatoire. */
export const SelectField: React.FC<SelectFieldProps> = ({
  label,
  hideLabel,
  hint,
  error,
  className,
  inputClassName,
  id: explicitId,
  children,
  ...props
}) => {
  const ids = useFieldIds(explicitId);
  return (
    <FieldShell
      {...ids}
      label={label}
      hideLabel={hideLabel}
      hint={hint}
      error={error}
      className={className}
    >
      <select
        {...props}
        id={ids.id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint, error, ids)}
        className={fieldClasses({
          invalid: Boolean(error),
          className: cn('pr-10', inputClassName),
        })}
      >
        {children}
      </select>
    </FieldShell>
  );
};
