import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { SelectField, TextAreaField, TextField } from './Field';

afterEach(cleanup);

describe('TextField', () => {
  it('associe réellement le libellé au champ', () => {
    render(<TextField label="Nom complet" defaultValue="" />);

    expect(screen.getByLabelText('Nom complet').tagName).toBe('INPUT');
  });

  it('relie l’aide au champ par aria-describedby', () => {
    render(<TextField label="Numéro" hint="Format international, ex. +221..." />);

    const input = screen.getByLabelText('Numéro');
    const hint = screen.getByText('Format international, ex. +221...');
    expect(input).toHaveAttribute('aria-describedby', hint.id);
    expect(input).not.toHaveAttribute('aria-invalid');
  });

  it('signale l’erreur (aria-invalid + annonce immédiate) à la place de l’aide', () => {
    render(<TextField label="Numéro" hint="Aide" error="Numéro invalide." />);

    const input = screen.getByLabelText('Numéro');
    const error = screen.getByRole('alert');
    expect(error).toHaveTextContent('Numéro invalide.');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAttribute('aria-describedby', error.id);
    expect(screen.queryByText('Aide')).not.toBeInTheDocument();
  });

  it('garde un libellé lisible par les lecteurs d’écran même masqué visuellement', () => {
    render(<TextField label="Rechercher" hideLabel />);

    expect(screen.getByLabelText('Rechercher')).toBeInTheDocument();
    expect(screen.getByText('Rechercher')).toHaveClass('sr-only');
  });
});

describe('TextAreaField', () => {
  it('associe le libellé à la zone de texte', () => {
    render(<TextAreaField label="Bio" />);

    expect(screen.getByLabelText('Bio').tagName).toBe('TEXTAREA');
  });
});

describe('SelectField', () => {
  it('associe le libellé à la liste déroulante', () => {
    render(
      <SelectField label="Métier" defaultValue="">
        <option value="">Choisir</option>
      </SelectField>,
    );

    expect(screen.getByLabelText('Métier').tagName).toBe('SELECT');
  });
});
