import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import App, { AppRoutes } from './App';

afterEach(cleanup);

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('App', () => {
  it('renders the landing screen without crashing', () => {
    render(<App />);

    expect(screen.getByText(/Un artisan de confiance/i)).toBeInTheDocument();
  });
});

describe('routing', () => {
  it('renders the landing screen at /', () => {
    renderAt('/');
    expect(screen.getByText(/Un artisan de confiance/i)).toBeInTheDocument();
  });

  it('renders the client home screen at /accueil', () => {
    renderAt('/accueil');
    expect(screen.getByPlaceholderText(/Décrivez votre besoin/i)).toBeInTheDocument();
  });

  it('renders the search screen at /recherche', () => {
    renderAt('/recherche');
    expect(screen.getByText(/Recherche d.artisans/i)).toBeInTheDocument();
  });

  it('renders the describe-problem screen at /demande, without the bottom nav', () => {
    renderAt('/demande');
    expect(screen.getByText('Décrivez votre problème')).toBeInTheDocument();
    expect(screen.queryByText('Recherche')).not.toBeInTheDocument();
  });

  it('renders the artisan dashboard at /pro', () => {
    renderAt('/pro');
    expect(screen.getByText(/Prêt pour vos services d.aujourd.hui/i)).toBeInTheDocument();
  });

  it('renders the user profile screen at /profil', () => {
    renderAt('/profil');
    expect(screen.getByText('Moyens de paiement au Sénégal')).toBeInTheDocument();
  });

  it('renders the artisan profile for a known id at /artisans/:artisanId', async () => {
    renderAt('/artisans/idrissa-diop');
    expect(screen.getByText('Profil Artisan')).toBeInTheDocument();
    expect(await screen.findByText('Idrissa Diop')).toBeInTheDocument();
  });

  it('renders the chat for a known conversation at /messages/:conversationId', async () => {
    renderAt('/messages/idrissa-diop');
    expect(await screen.findByText('Idrissa Diop')).toBeInTheDocument();
  });

  it('renders a 404 with a link back to /accueil for an unknown route', () => {
    renderAt('/this-route-does-not-exist');

    expect(screen.getByText('Page introuvable')).toBeInTheDocument();
    const backLink = screen.getByRole('link', { name: /Retour à l.accueil/i });
    expect(backLink).toHaveAttribute('href', '/accueil');
  });

  it('shows the existing error state (not a crash or blank screen) for an unknown artisan id', async () => {
    renderAt('/artisans/does-not-exist');

    expect(
      await screen.findByText("Cet artisan n'existe pas ou n'est plus disponible."),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Réessayer' })).toBeInTheDocument();

    // The header's back link stays available as the way out of the error state.
    const links = screen.getAllByRole('link');
    expect(links.some((link) => link.getAttribute('href') === '/accueil')).toBe(true);
  });
});
