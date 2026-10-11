import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ComingSoon } from './ComingSoon';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { Skeleton } from './Skeleton';
import { PageLoader, Spinner } from './Spinner';

afterEach(cleanup);

describe('EmptyState', () => {
  it('explique l’absence de contenu et propose une action', () => {
    const onClick = vi.fn();
    render(
      <EmptyState
        title="Aucun artisan trouvé."
        description="Essayez un autre métier."
        action={{ label: 'Réinitialiser les filtres', onClick }}
      />,
    );

    expect(screen.getByText('Aucun artisan trouvé.')).toBeInTheDocument();
    expect(screen.getByText('Essayez un autre métier.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Réinitialiser les filtres' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('accepte des actions personnalisées (liens)', () => {
    render(
      <EmptyState title="Rien ici.">
        <a href="/demande">Décrire mon problème</a>
      </EmptyState>,
    );

    expect(screen.getByRole('link', { name: 'Décrire mon problème' })).toBeInTheDocument();
  });
});

describe('ErrorState', () => {
  it('annonce l’erreur et relance le chargement', () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Le serveur est injoignable." onRetry={onRetry} />);

    expect(screen.getByRole('alert')).toHaveTextContent('Le serveur est injoignable.');

    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe('Skeleton', () => {
  it('reste invisible pour les lecteurs d’écran', () => {
    const { container } = render(<Skeleton className="h-4" />);

    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('Spinner', () => {
  it('annonce le chargement avec un libellé', () => {
    render(<Spinner label="Envoi" />);

    expect(screen.getByRole('status', { name: 'Envoi' })).toBeInTheDocument();
  });

  it('est muet quand il est décoratif', () => {
    render(<Spinner label={null} />);

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('propose un chargement plein écran', () => {
    render(<PageLoader />);

    expect(screen.getByRole('status', { name: 'Chargement' })).toBeInTheDocument();
  });
});

describe('ComingSoon', () => {
  it('affiche un « pas encore » honnête avec un lien de retour', () => {
    render(
      <MemoryRouter>
        <ComingSoon title="La messagerie arrive bientôt" backTo="/pro" />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { level: 1, name: 'La messagerie arrive bientôt' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Retour/ })).toHaveAttribute('href', '/pro');
  });
});
