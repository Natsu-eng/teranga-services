import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { Button, ButtonLink } from './Button';
import { IconButton } from './IconButton';

afterEach(cleanup);

describe('Button', () => {
  it('ne soumet jamais un formulaire par défaut (type="button")', () => {
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button>Action</Button>
      </form>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Action' }));

    expect(screen.getByRole('button', { name: 'Action' })).toHaveAttribute('type', 'button');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('soumet le formulaire quand type="submit" est explicite', () => {
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button type="submit">Valider</Button>
      </form>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Valider' }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('désactive le bouton et signale aria-busy pendant un chargement, sans déclencher le clic', () => {
    const onClick = vi.fn();
    render(
      <Button isLoading onClick={onClick}>
        Envoi en cours...
      </Button>,
    );

    const button = screen.getByRole('button', { name: 'Envoi en cours...' });
    fireEvent.click(button);

    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(onClick).not.toHaveBeenCalled();
  });

  it('applique la variante or (primary) avec un texte vert profond lisible', () => {
    render(<Button variant="primary">Demander un devis</Button>);

    const button = screen.getByRole('button', { name: 'Demander un devis' });
    expect(button.className).toContain('bg-accent');
    expect(button.className).toContain('text-primary');
  });

  it('étend le bouton sur toute la largeur avec fullWidth', () => {
    render(<Button fullWidth>Continuer</Button>);

    expect(screen.getByRole('button', { name: 'Continuer' }).className).toContain('w-full');
  });
});

describe('ButtonLink', () => {
  it('rend un vrai lien de navigation habillé en bouton', () => {
    render(
      <MemoryRouter>
        <ButtonLink to="/demande" variant="primary">
          Décrire mon problème
        </ButtonLink>
      </MemoryRouter>,
    );

    const link = screen.getByRole('link', { name: 'Décrire mon problème' });
    expect(link).toHaveAttribute('href', '/demande');
    expect(link.className).toContain('rounded-full');
  });
});

describe('IconButton', () => {
  it('expose son libellé comme nom accessible', () => {
    const onClick = vi.fn();
    render(
      <IconButton label="Partager le profil" onClick={onClick}>
        <svg />
      </IconButton>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Partager le profil' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
