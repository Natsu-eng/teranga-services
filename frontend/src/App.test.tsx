import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import App, { AppRoutes } from './App';
import { authStore } from './lib/api/auth-store';

// App-level tests are routing/layout smoke tests, not data-fetching
// fidelity tests (that's covered by http.test.ts and http-impl.test.ts,
// which mock at the fetch boundary). They exercise the mock backend
// directly rather than the real one, so no network call is needed here.
vi.mock('./lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./lib/api')>();
  const { mockApiClient } = await import('./lib/api/mock');
  return { ...actual, api: mockApiClient };
});

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? '' : JSON.stringify(body)),
  } as Response;
}

beforeEach(() => {
  authStore.clear();
  authStore.onForcedLogout(null);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

/** Simulates an already-logged-in visitor: a persisted refresh token that AuthProvider silently exchanges for a fresh session on mount. */
function stubAuthenticatedSession() {
  authStore.setTokens({ access: '', refresh: 'persisted-refresh' });
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/me')) {
        return authStore.getAccessToken() === 'fresh-access'
          ? Promise.resolve(
              jsonResponse(200, {
                id: 'u1',
                phone: '+221771234501',
                full_name: 'Diandé Diallo',
                role: 'client',
                locale: 'fr',
                phone_verified_at: '2026-01-01T00:00:00Z',
              }),
            )
          : Promise.resolve(jsonResponse(401, { error: { code: 'TOKEN_INVALIDE', message: 'x' } }));
      }
      if (url.endsWith('/auth/refresh')) {
        return Promise.resolve(jsonResponse(200, { access: 'fresh-access', refresh: 'fresh-refresh' }));
      }
      throw new Error(`unexpected fetch: ${url}`);
    }),
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

  it('redirects to /connexion when visiting the (protected) artisan dashboard at /pro without a session', async () => {
    renderAt('/pro');
    expect(await screen.findByRole('heading', { name: 'Connexion' })).toBeInTheDocument();
  });

  it('redirects to /connexion when visiting the (protected) user profile at /profil without a session', async () => {
    renderAt('/profil');
    expect(await screen.findByRole('heading', { name: 'Connexion' })).toBeInTheDocument();
  });

  it('renders the artisan profile for a known id at /artisans/:artisanId', async () => {
    renderAt('/artisans/idrissa-diop');
    expect(screen.getByText('Profil Artisan')).toBeInTheDocument();
    expect(await screen.findByText('Idrissa Diop')).toBeInTheDocument();
  });

  it('redirects to /connexion when visiting the (protected) chat at /messages/:conversationId without a session', async () => {
    renderAt('/messages/idrissa-diop');
    expect(await screen.findByRole('heading', { name: 'Connexion' })).toBeInTheDocument();
  });

  it('renders the phone screen at /connexion', () => {
    renderAt('/connexion');
    expect(screen.getByRole('heading', { name: 'Connexion' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('+221771234567')).toBeInTheDocument();
  });

  it('sends /connexion/code back to /connexion when reached directly (no phone in navigation state)', async () => {
    renderAt('/connexion/code');
    expect(await screen.findByRole('heading', { name: 'Connexion' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('+221771234567')).toBeInTheDocument();
  });

  it('grants access to the (protected) profile once a session is restored from a persisted refresh token', async () => {
    stubAuthenticatedSession();

    renderAt('/profil');

    await waitFor(() => expect(screen.getByText('Moyens de paiement au Sénégal')).toBeInTheDocument());
  });

  it('shows the honest "coming soon" state (not the old mock dashboard) at /pro once authenticated', async () => {
    stubAuthenticatedSession();

    renderAt('/pro');

    expect(await screen.findByText("L'espace Artisan Pro arrive bientôt")).toBeInTheDocument();
  });

  it('shows the honest "coming soon" state (not the old mock chat) at /messages/:conversationId once authenticated', async () => {
    stubAuthenticatedSession();

    renderAt('/messages/idrissa-diop');

    expect(await screen.findByText('La messagerie arrive bientôt')).toBeInTheDocument();
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
