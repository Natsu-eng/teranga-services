import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { ArtisanProfileScreen } from './ArtisanProfileScreen';
import { useArtisan } from './hooks/useArtisan';
import { useMyRequests } from '../requests/hooks/useMyRequests';
import { useAuth } from '../auth/hooks/useAuth';
import { api, ApiError } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { AuthUser } from '../../lib/api/auth-client';
import type { Artisan, Intervention, ServiceRequest } from '../../types';

vi.mock('./hooks/useArtisan');
vi.mock('../requests/hooks/useMyRequests');
vi.mock('../auth/hooks/useAuth');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: { ...actual.api, createIntervention: vi.fn(), listConversations: vi.fn() },
  };
});

const mockedUseArtisan = vi.mocked(useArtisan);
const mockedUseMyRequests = vi.mocked(useMyRequests);
const mockedUseAuth = vi.mocked(useAuth);
const mockedCreateIntervention = vi.mocked(api.createIntervention);
const mockedListConversations = vi.mocked(api.listConversations);

const artisanFixture: Artisan = {
  id: 'test-artisan',
  name: 'Aissatou Sow',
  trade: 'Plomberie',
  avatarUrl: '/images/test-avatar.jpg',
  coverUrl: '/images/test-cover.jpg',
  verified: true,
  rating: 4.7,
  reviewCount: 10,
  distance: '1 km',
  location: 'Dakar, Sénégal',
  priceBase: '10.000 CFA',
  priceNumber: 10000,
  tags: ['Plomberie'],
  tradeCodes: ['plomberie'],
  bio: 'Bio de test pour la fiche artisan.',
  stats: { chantiers: '10+', responseTime: '< 1h', experience: '2 ans' },
  realisations: [],
  reviews: [],
  available: true,
};

function requestFixture(overrides: Partial<ServiceRequest>): ServiceRequest {
  return {
    id: 'req-1',
    tradeCode: 'plomberie',
    tradeLabel: 'Plomberie',
    description: 'Fuite sous l’évier de la cuisine.',
    photoUrl: null,
    location: { lat: 14.69, lng: -17.44 },
    urgency: 'normal',
    aiEstimateMinFcfa: null,
    aiEstimateMaxFcfa: null,
    status: 'ouverte',
    createdAt: '2026-10-01T10:00:00Z',
    ...overrides,
  };
}

function authValue(overrides: Partial<AuthContextValue>): AuthContextValue {
  return {
    user: null,
    role: null,
    isAuthenticated: false,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    updateFullName: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

function signedIn(role: AuthUser['role'], artisanProfileId: string | null = null) {
  return authValue({
    isAuthenticated: true,
    role,
    user: {
      id: 'u1',
      phone: '+221770000000',
      fullName: 'Awa Diop',
      role,
      locale: 'fr',
      phoneVerifiedAt: '2026-01-01T00:00:00Z',
      artisanProfileId,
    },
  });
}

function LocationProbe() {
  const location = useLocation();
  return <div>Page {location.pathname + location.search}</div>;
}

function renderAtArtisan(artisanId: string) {
  return render(
    <MemoryRouter initialEntries={[`/artisans/${artisanId}`]}>
      <Routes>
        <Route path="/artisans/:artisanId" element={<ArtisanProfileScreen />} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

function withArtisan(artisan: Artisan = artisanFixture) {
  mockedUseArtisan.mockReturnValue({
    data: artisan,
    isLoading: false,
    error: null,
    reload: vi.fn(),
    setData: vi.fn(),
  });
}

describe('ArtisanProfileScreen', () => {
  beforeEach(() => {
    mockedUseArtisan.mockReset();
    mockedCreateIntervention.mockReset();
    mockedListConversations.mockReset();
    mockedUseAuth.mockReturnValue(authValue({}));
    mockedUseMyRequests.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });
  });

  afterEach(cleanup);

  it('shows a loading skeleton while the artisan is being fetched', () => {
    mockedUseArtisan.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
      reload: vi.fn(),
      setData: vi.fn(),
    });

    const { container } = renderAtArtisan('test-artisan');

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
    expect(screen.queryByText(artisanFixture.name)).not.toBeInTheDocument();
  });

  it('shows an error state with a working retry button', () => {
    const reload = vi.fn();
    mockedUseArtisan.mockReturnValue({
      data: null,
      isLoading: false,
      error: new ApiError('not_found', "Cet artisan n'existe pas ou n'est plus disponible."),
      reload,
      setData: vi.fn(),
    });

    renderAtArtisan('missing');

    expect(
      screen.getByText("Cet artisan n'existe pas ou n'est plus disponible."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('renders the artisan profile on success', () => {
    withArtisan();

    renderAtArtisan(artisanFixture.id);

    expect(screen.getByText(artisanFixture.name)).toBeInTheDocument();
    expect(screen.getByText(artisanFixture.bio)).toBeInTheDocument();
  });

  it('affiche le badge Vérifié en grand pour un artisan vérifié', () => {
    withArtisan();

    renderAtArtisan(artisanFixture.id);

    expect(screen.getByText('Vérifié').className).toContain('h-9');
  });

  it('n’affiche aucun numéro de téléphone sur la fiche', () => {
    withArtisan();

    const { container } = renderAtArtisan(artisanFixture.id);

    expect(container.textContent).not.toMatch(/\+?\d[\d\s]{7,}/);
    expect(container.querySelector('a[href^="tel:"]')).toBeNull();
  });

  describe('Demander un devis', () => {
    it('envoie un visiteur se connecter, avec retour prévu sur la fiche', () => {
      withArtisan();

      renderAtArtisan(artisanFixture.id);
      fireEvent.click(screen.getByRole('button', { name: 'Demander un devis' }));

      expect(screen.getByText('Page /connexion')).toBeInTheDocument();
    });

    it('propose au client sa demande ouverte compatible, puis crée la mise en relation', async () => {
      mockedUseAuth.mockReturnValue(signedIn('client'));
      mockedUseMyRequests.mockReturnValue({
        data: [
          requestFixture({ id: 'req-plomberie' }),
          // Jamais proposées : autre métier, ou demande déjà en relation.
          requestFixture({ id: 'req-elec', tradeCode: 'electricite', tradeLabel: 'Électricité' }),
          requestFixture({ id: 'req-close', status: 'en_relation' }),
        ],
        isLoading: false,
        error: null,
        reload: vi.fn(),
      });
      mockedCreateIntervention.mockResolvedValue({ id: 'int-1' } as Intervention);
      withArtisan();

      renderAtArtisan(artisanFixture.id);
      fireEvent.click(screen.getByRole('button', { name: 'Demander un devis' }));

      const dialog = screen.getByRole('dialog', { name: 'Demander un devis' });
      expect(within(dialog).getAllByRole('radio')).toHaveLength(1);
      expect(within(dialog).getByRole('radio')).toBeChecked();

      fireEvent.click(within(dialog).getByRole('button', { name: 'Envoyer à Aissatou' }));

      expect(mockedCreateIntervention).toHaveBeenCalledWith({
        serviceRequestId: 'req-plomberie',
        artisanId: 'test-artisan',
      });
      expect(await within(dialog).findByText('Demande envoyée à Aissatou')).toBeInTheDocument();
      expect(
        within(dialog).getByRole('link', { name: 'Suivre mes devis et travaux' }),
      ).toHaveAttribute('href', '/mes-interventions');
    });

    it('affiche le refus du serveur sans fermer le panneau', async () => {
      mockedUseAuth.mockReturnValue(signedIn('client'));
      mockedUseMyRequests.mockReturnValue({
        data: [requestFixture({})],
        isLoading: false,
        error: null,
        reload: vi.fn(),
      });
      mockedCreateIntervention.mockRejectedValue(
        new ApiError('validation', "Cet artisan n'intervient pas dans votre zone."),
      );
      withArtisan();

      renderAtArtisan(artisanFixture.id);
      fireEvent.click(screen.getByRole('button', { name: 'Demander un devis' }));
      fireEvent.click(screen.getByRole('button', { name: 'Envoyer à Aissatou' }));

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent(
          "Cet artisan n'intervient pas dans votre zone.",
        ),
      );
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('sans demande compatible, invite à décrire le besoin pour CET artisan', () => {
      mockedUseAuth.mockReturnValue(signedIn('client'));
      withArtisan();

      renderAtArtisan(artisanFixture.id);
      fireEvent.click(screen.getByRole('button', { name: 'Demander un devis' }));

      expect(screen.getByRole('link', { name: 'Décrire mon besoin' })).toHaveAttribute(
        'href',
        '/demande?artisan=test-artisan',
      );
      expect(mockedCreateIntervention).not.toHaveBeenCalled();
    });

    it('se ferme avec Échap', () => {
      mockedUseAuth.mockReturnValue(signedIn('client'));
      withArtisan();

      renderAtArtisan(artisanFixture.id);
      fireEvent.click(screen.getByRole('button', { name: 'Demander un devis' }));
      fireEvent.keyDown(document, { key: 'Escape' });

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('est indisponible tant que l’artisan n’est pas vérifié', () => {
      withArtisan({ ...artisanFixture, verified: false });

      renderAtArtisan(artisanFixture.id);

      expect(screen.getByRole('button', { name: 'Demander un devis' })).toBeDisabled();
      expect(screen.queryByText('Vérifié')).not.toBeInTheDocument();
    });

    it('n’est jamais proposé à un artisan, qui peut seulement modifier SA fiche', () => {
      mockedUseAuth.mockReturnValue(signedIn('artisan', 'test-artisan'));
      withArtisan();

      renderAtArtisan(artisanFixture.id);

      expect(screen.queryByRole('button', { name: 'Demander un devis' })).not.toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Modifier ma fiche' })).toHaveAttribute(
        'href',
        '/pro/onboarding',
      );
    });

    it('ne propose aucune action à un artisan sur la fiche d’un confrère', () => {
      mockedUseAuth.mockReturnValue(signedIn('artisan', 'autre-artisan'));
      withArtisan();

      renderAtArtisan(artisanFixture.id);

      expect(screen.queryByRole('button', { name: 'Demander un devis' })).not.toBeInTheDocument();
      expect(screen.queryByRole('link', { name: 'Modifier ma fiche' })).not.toBeInTheDocument();
    });
  });

  describe('Message', () => {
    it('ouvre le fil existant avec cet artisan', async () => {
      mockedUseAuth.mockReturnValue(signedIn('client'));
      mockedListConversations.mockResolvedValue([
        { id: 'fil-42' } as Awaited<ReturnType<typeof api.listConversations>>[number],
      ]);
      withArtisan();

      renderAtArtisan(artisanFixture.id);
      fireEvent.click(screen.getByRole('button', { name: 'Message' }));

      expect(await screen.findByText('Page /messages/fil-42')).toBeInTheDocument();
      expect(mockedListConversations).toHaveBeenCalledWith({ artisanId: 'test-artisan' });
    });

    it("sans mise en relation, explique et propose d'envoyer une demande (aucun canal libre)", async () => {
      mockedUseAuth.mockReturnValue(signedIn('client'));
      mockedListConversations.mockResolvedValue([]);
      withArtisan();

      renderAtArtisan(artisanFixture.id);
      fireEvent.click(screen.getByRole('button', { name: 'Message' }));

      const dialog = await screen.findByRole('dialog', { name: 'Demander un devis' });
      expect(
        within(dialog).getByText(/s'ouvre dès que vous lui envoyez une demande/),
      ).toBeInTheDocument();
    });

    it('envoie un visiteur se connecter', () => {
      withArtisan();

      renderAtArtisan(artisanFixture.id);
      fireEvent.click(screen.getByRole('button', { name: 'Message' }));

      expect(screen.getByText('Page /connexion')).toBeInTheDocument();
      expect(mockedListConversations).not.toHaveBeenCalled();
    });
  });
});
