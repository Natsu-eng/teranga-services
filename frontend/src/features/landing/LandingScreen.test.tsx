import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { LandingScreen } from './LandingScreen';

afterEach(cleanup);

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingScreen />
    </MemoryRouter>,
  );
}

describe('LandingScreen', () => {
  it('présente la promesse et une seule action principale vers la recherche', () => {
    renderLanding();

    expect(
      screen.getByRole('heading', { level: 1, name: /Un artisan de confiance/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Trouver un artisan/ })).toHaveAttribute(
      'href',
      '/accueil',
    );
    expect(screen.getByRole('link', { name: /Vous êtes artisan/ })).toHaveAttribute(
      'href',
      '/connexion',
    );
  });

  it('montre le badge Vérifié tel qu’il apparaît ensuite sur les cartes', () => {
    renderLanding();

    expect(screen.getByText('Vérifié')).toBeInTheDocument();
  });

  it('n’affiche aucun chiffre ni promesse invérifiable (note, volume, paiement)', () => {
    renderLanding();

    expect(screen.queryByText(/4[.,]8/)).not.toBeInTheDocument();
    expect(screen.queryByText(/250\+/)).not.toBeInTheDocument();
    expect(screen.queryByText(/paiement/i)).not.toBeInTheDocument();
  });
});
