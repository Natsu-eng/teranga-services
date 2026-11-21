import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router';
import { DescribeProblemScreen } from './DescribeProblemScreen';
import { useArtisans } from '../artisans/hooks/useArtisans';
import { useArtisan } from '../artisans/hooks/useArtisan';
import { useTrades } from '../artisans/hooks/useTrades';
import { useAnalyzeProblem } from './hooks/useAnalyzeProblem';
import { useAuth } from '../auth/hooks/useAuth';
import { GeolocationError, getCurrentPosition } from '../../lib/geo';
import { PlaceProvider, PLACE_STORAGE_KEY } from '../location/PlaceProvider';
import { TEST_CATALOG } from '../../testing/neighborhoodCatalog';
import { distanceFromRegionCenterKm, findNeighborhood } from '../../lib/places';
import { LocationPicker } from '../../components/layout/LocationPicker';
import { api, ApiError } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { AIAnalysisResult, Artisan, Intervention, ServiceRequest } from '../../types';

vi.mock('../artisans/hooks/useArtisans');
vi.mock('../artisans/hooks/useArtisan');
vi.mock('../artisans/hooks/useTrades');
vi.mock('./hooks/useAnalyzeProblem');
vi.mock('../auth/hooks/useAuth');
vi.mock('../../lib/geo', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/geo')>();
  return { ...actual, getCurrentPosition: vi.fn() };
});
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      createServiceRequest: vi.fn(),
      createIntervention: vi.fn(),
      checkArtisanCoverage: vi.fn(),
    },
  };
});

const mockedUseArtisans = vi.mocked(useArtisans);
const mockedUseArtisan = vi.mocked(useArtisan);
const mockedUseTrades = vi.mocked(useTrades);

// Liste réelle des métiers (forme de GET /trades).
const TRADES = [
  { id: 't1', code: 'plomberie', labelFr: 'Plomberie' },
  { id: 't2', code: 'electricite', labelFr: 'Électricité' },
  { id: 't3', code: 'menuiserie', labelFr: 'Menuiserie' },
];
const mockedCreateIntervention = vi.mocked(api.createIntervention);
const mockedUseAnalyzeProblem = vi.mocked(useAnalyzeProblem);
const mockedUseAuth = vi.mocked(useAuth);
const mockedGetCurrentPosition = vi.mocked(getCurrentPosition);
const mockedCreateServiceRequest = vi.mocked(api.createServiceRequest);
const mockedCheckCoverage = vi.mocked(api.checkArtisanCoverage);

// Centre du Plateau, quartier par défaut (catalogue servi par le serveur).
const PLATEAU_ENTRY = TEST_CATALOG.items.find((item) => item.id === TEST_CATALOG.defaultId)!;
const PLATEAU = { lat: PLATEAU_ENTRY.lat, lng: PLATEAU_ENTRY.lng };

const artisanFixture: Artisan = {
  id: 'a1',
  name: 'Maty Ndiaye',
  trade: 'Électricité',
  avatarUrl: null,
  coverUrl: null,
  verified: true,
  rating: 4.9,
  reviewCount: 5,
  distance: '1 km',
  priceBase: 'Tarif sur devis',
  priceNumber: 0,
  tags: ['Électricité'],
  tradeCodes: ['electricite'],
  bio: '',
  stats: { experience: '6 ans' },
  realisations: [],
  reviews: [],
  available: true,
};

const aiResultFixture: AIAnalysisResult = {
  trade: 'Électricité',
  tradeCode: 'electricite',
  urgency: 'haute',
  urgencyCode: 'urgent',
};

const serviceRequestFixture: ServiceRequest = {
  id: 'req-1',
  tradeCode: 'electricite',
  tradeLabel: 'Électricité',
  description: 'Une prise ne fonctionne plus.',
  photoUrl: null,
  location: { lat: 1, lng: 2 },
  locationLabel: null,
  urgency: 'urgent',
  status: 'ouverte',
  expiresAt: null,
  createdAt: '2026-01-01T00:00:00Z',
};

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

function SearchParamsProbe() {
  const [searchParams] = useSearchParams();
  return <div>Search results for {searchParams.toString()}</div>;
}

function renderScreen(path = '/demande') {
  return render(
    <PlaceProvider initialCatalog={TEST_CATALOG}>
      {/* Le sélecteur de l'en-tête partage le lieu avec l'écran. */}
      <LocationPicker />
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/demande" element={<DescribeProblemScreen />} />
          <Route path="/connexion" element={<div>Login screen</div>} />
          <Route path="/recherche" element={<SearchParamsProbe />} />
          <Route path="/mes-interventions" element={<div>Mes interventions</div>} />
        </Routes>
      </MemoryRouter>
    </PlaceProvider>,
  );
}

const DESCRIPTION = 'Une prise ne fonctionne plus dans le salon.';

/** Saisit une vraie description : l'envoi exige un texte suffisant. */
function describeProblem(text = DESCRIPTION) {
  fireEvent.change(screen.getByLabelText('Votre problème'), { target: { value: text } });
}

describe('DescribeProblemScreen', () => {
  beforeEach(() => {
    mockedUseTrades.mockReturnValue({
      data: TRADES,
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });
    mockedUseArtisans.mockReturnValue({
      data: [artisanFixture],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });
    mockedUseAnalyzeProblem.mockReturnValue({
      data: aiResultFixture,
      isLoading: false,
      error: null,
      analyze: vi.fn(),
    });
    window.localStorage.removeItem(PLACE_STORAGE_KEY);
    mockedGetCurrentPosition.mockReset().mockResolvedValue({ lat: 14.7225, lng: -17.4878 });
    mockedCheckCoverage.mockReset().mockResolvedValue({ eligible: true, reason: null });
    mockedCreateServiceRequest.mockReset();
    mockedCreateServiceRequest.mockResolvedValue(serviceRequestFixture);
    mockedCreateIntervention.mockReset();
    mockedUseArtisan.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
      reload: vi.fn(),
      setData: vi.fn(),
    });
  });

  afterEach(cleanup);

  it('creates a service request with the AI-detected trade code and lands on a server-filtered search', async () => {
    mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));

    renderScreen();
    describeProblem();
    fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));

    await waitFor(() => expect(mockedCreateServiceRequest).toHaveBeenCalledTimes(1));
    expect(mockedCreateServiceRequest).toHaveBeenCalledWith(
      expect.objectContaining({
        tradeCode: 'electricite',
        description: DESCRIPTION,
        photoUrl: null,
        urgency: 'urgent',
        // Le lieu affiché et confirmé (quartier par défaut), pas le GPS.
        location: PLATEAU,
        locationLabel: 'Dakar-Plateau',
      }),
    );
    // Plus aucune estimation de prix transmise (chiffre sans fondement réel).
    const sent = mockedCreateServiceRequest.mock.calls[0][0];
    expect(sent).not.toHaveProperty('aiEstimateMinFcfa');
    expect(sent).not.toHaveProperty('aiEstimateMaxFcfa');
    expect(mockedGetCurrentPosition).not.toHaveBeenCalled();

    const results = await screen.findByText(/Search results for/);
    expect(results.textContent).toContain('trade=electricite');
    expect(results.textContent).toContain(`lat=${PLATEAU.lat}`);
    expect(results.textContent).toContain(`lng=${PLATEAU.lng}`);
  });

  describe('métier proposé, jamais imposé', () => {
    it('présente le métier comme une proposition, modifiable dans la vraie liste', () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));
      renderScreen();
      describeProblem();

      const select = screen.getByLabelText('Métier proposé') as HTMLSelectElement;
      expect(select.value).toBe('electricite');
      expect(
        within(select)
          .getAllByRole('option')
          .map((option) => option.textContent),
      ).toEqual(['Plomberie', 'Électricité', 'Menuiserie']);
      expect(screen.getByText(/Proposé d'après votre description/)).toBeInTheDocument();
      expect(screen.queryByText('Métier détecté')).toBeNull();
    });

    it("sans métier reconnu : le dit, et n'autorise l'envoi qu'après un choix du client", async () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));
      mockedUseAnalyzeProblem.mockReturnValue({
        data: { trade: null, tradeCode: null, urgency: 'normale', urgencyCode: 'normal' },
        isLoading: false,
        error: null,
        analyze: vi.fn(),
      });
      renderScreen();
      describeProblem();

      expect(screen.getByText(/Nous n'avons pas reconnu le métier/)).toBeInTheDocument();
      const submit = screen.getByRole('button', { name: /Voir les artisans/ });
      expect(submit).toBeDisabled();

      fireEvent.change(screen.getByLabelText('Métier'), { target: { value: 'menuiserie' } });
      expect(submit).toBeEnabled();
      fireEvent.click(submit);

      await waitFor(() => expect(mockedCreateServiceRequest).toHaveBeenCalledTimes(1));
      expect(mockedCreateServiceRequest.mock.calls[0][0].tradeCode).toBe('menuiserie');
    });

    it('le choix du client prime sur la proposition', async () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));
      renderScreen();
      describeProblem();

      fireEvent.change(screen.getByLabelText('Métier proposé'), { target: { value: 'plomberie' } });
      expect(screen.getByLabelText('Métier choisi')).toHaveValue('plomberie');
      fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));

      await waitFor(() => expect(mockedCreateServiceRequest).toHaveBeenCalledTimes(1));
      expect(mockedCreateServiceRequest.mock.calls[0][0].tradeCode).toBe('plomberie');
    });
  });

  it('redirects to /connexion instead of creating a request when signed out', async () => {
    mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: false }));

    renderScreen();
    describeProblem();
    fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));

    expect(await screen.findByText('Login screen')).toBeInTheDocument();
    expect(mockedCreateServiceRequest).not.toHaveBeenCalled();
  });

  it("shows the backend's error message when request creation fails", async () => {
    mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));
    mockedCreateServiceRequest.mockRejectedValue(
      new ApiError('validation', 'Le métier demandé est introuvable ou inactif.'),
    );

    renderScreen();
    describeProblem();
    fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));

    expect(
      await screen.findByText('Le métier demandé est introuvable ou inactif.'),
    ).toBeInTheDocument();
  });

  describe('analyse IA', () => {
    afterEach(() => vi.useRealTimers());

    it('n’appelle l’IA qu’après une pause de frappe, jamais à chaque caractère', () => {
      vi.useFakeTimers();
      const analyze = vi.fn();
      mockedUseAnalyzeProblem.mockReturnValue({
        data: null,
        isLoading: false,
        error: null,
        analyze,
      });
      mockedUseAuth.mockReturnValue(authValue({}));

      renderScreen();
      describeProblem('Une prise ne');
      describeProblem('Une prise ne fonctionne');
      describeProblem(DESCRIPTION);
      expect(analyze).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(900);
      });

      expect(analyze).toHaveBeenCalledTimes(1);
      expect(analyze).toHaveBeenCalledWith(DESCRIPTION);
    });

    it('ne lance aucune analyse sur une description trop courte', () => {
      vi.useFakeTimers();
      const analyze = vi.fn();
      mockedUseAnalyzeProblem.mockReturnValue({
        data: null,
        isLoading: false,
        error: null,
        analyze,
      });
      mockedUseAuth.mockReturnValue(authValue({}));

      renderScreen();
      describeProblem('Fuite');
      act(() => {
        vi.advanceTimersByTime(2000);
      });

      expect(analyze).not.toHaveBeenCalled();
    });

    it('ne préremplit plus aucune description ni contenu simulé', () => {
      mockedUseAuth.mockReturnValue(authValue({}));

      renderScreen();

      expect(screen.getByLabelText('Votre problème')).toHaveValue('');
      expect(screen.queryByRole('button', { name: /vocal/i })).not.toBeInTheDocument();
    });

    it('n’autorise pas l’envoi tant que la description est insuffisante', () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));

      renderScreen();

      expect(screen.getByRole('button', { name: /Voir les artisans/ })).toBeDisabled();
    });

    it('réserve la création de demande aux clients', () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'artisan' }));

      renderScreen();
      describeProblem();

      expect(screen.getByRole('button', { name: /Voir les artisans/ })).toBeDisabled();
      expect(screen.getByText(/réservée aux comptes clients/)).toBeInTheDocument();
    });
  });

  describe('demande adressée depuis une fiche artisan (?artisan=)', () => {
    function targetArtisan(tradeCodes: string[]) {
      mockedUseArtisan.mockReturnValue({
        data: { ...artisanFixture, id: 'a1', name: 'Maty Ndiaye', tradeCodes },
        isLoading: false,
        error: null,
        reload: vi.fn(),
        setData: vi.fn(),
      });
    }

    it('envoie directement la demande à l’artisan visé quand le métier correspond', async () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));
      targetArtisan(['electricite']);
      mockedCreateIntervention.mockResolvedValue({ id: 'int-1' } as Intervention);

      renderScreen('/demande?artisan=a1');
      expect(screen.getByText('Demande destinée à')).toBeInTheDocument();
      describeProblem();
      // Le bouton s'active une fois la zone confirmée par le serveur.
      const send = await screen.findByRole('button', { name: 'Envoyer à Maty Ndiaye' });
      await waitFor(() => expect(send).toBeEnabled());
      fireEvent.click(send);

      await waitFor(() =>
        expect(mockedCreateIntervention).toHaveBeenCalledWith({
          serviceRequestId: 'req-1',
          artisanId: 'a1',
        }),
      );
      expect(await screen.findByText('Mes interventions')).toBeInTheDocument();
    });

    it('signale un métier incompatible et revient au parcours normal (recherche)', async () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));
      targetArtisan(['plomberie']);

      renderScreen('/demande?artisan=a1');
      describeProblem();

      expect(screen.getByText(/ne fait pas partie des métiers de Maty Ndiaye/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));

      expect(await screen.findByText(/Search results for/)).toBeInTheDocument();
      expect(mockedCreateIntervention).not.toHaveBeenCalled();
    });

    it('si l’artisan refuse, garde la demande créée et propose les autres artisans sans la recréer', async () => {
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' }));
      targetArtisan(['electricite']);
      mockedCreateIntervention.mockRejectedValue(
        new ApiError('validation', "Cet artisan n'intervient pas dans votre zone."),
      );

      renderScreen('/demande?artisan=a1');
      describeProblem();
      // Le bouton s'active une fois la zone confirmée par le serveur.
      const send = await screen.findByRole('button', { name: 'Envoyer à Maty Ndiaye' });
      await waitFor(() => expect(send).toBeEnabled());
      fireEvent.click(send);

      expect(await screen.findByRole('alert')).toHaveTextContent(
        /n'intervient pas dans votre zone/,
      );
      const fallback = screen.getByRole('link', { name: /Voir les autres artisans/ });
      expect(fallback.getAttribute('href')).toContain('trade=electricite');
      expect(mockedCreateServiceRequest).toHaveBeenCalledTimes(1);
    });
  });

  describe("lieu de l'intervention (explicite)", () => {
    beforeEach(() =>
      mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true, role: 'client' })),
    );

    function submit() {
      describeProblem();
      fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));
    }

    it('affiche le lieu avant le bouton d’envoi, cohérent avec l’en-tête', () => {
      renderScreen();

      expect(screen.getByText(/Intervention à :/)).toHaveTextContent(
        'Intervention à : Dakar-Plateau',
      );
      expect(screen.getByLabelText('Quartier')).toHaveValue('plateau');
    });

    it('enregistre le quartier choisi, et l’en-tête suit', async () => {
      renderScreen();

      fireEvent.change(screen.getByLabelText('Quartier'), { target: { value: 'ouakam' } });
      expect(screen.getByText(/Intervention à :/)).toHaveTextContent('Ouakam');
      // Même valeur partagée : l'en-tête affiche le même quartier.
      expect(screen.getByRole('button', { name: /Quartier :\s*Ouakam/ })).toBeInTheDocument();
      submit();

      await waitFor(() => expect(mockedCreateServiceRequest).toHaveBeenCalledTimes(1));
      // Centre officiel servi par le serveur.
      const ouakam = findNeighborhood(TEST_CATALOG, 'ouakam')!;
      expect(mockedCreateServiceRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          location: { lat: ouakam.lat, lng: ouakam.lng },
          locationLabel: 'Ouakam',
        }),
      );
    });

    it('le quartier choisi dans l’en-tête devient le lieu de la demande', async () => {
      renderScreen();

      fireEvent.click(screen.getByRole('button', { name: /Quartier :\s*Dakar-Plateau/ }));
      fireEvent.click(screen.getByRole('button', { name: 'Fann-Point E-Amitié' }));
      submit();

      await waitFor(() =>
        expect(mockedCreateServiceRequest).toHaveBeenCalledWith(
          expect.objectContaining({ locationLabel: 'Fann-Point E-Amitié' }),
        ),
      );
    });

    it('propose la position GPS sans jamais l’imposer : montrée, puis confirmée', async () => {
      renderScreen();

      fireEvent.click(screen.getByRole('button', { name: 'Utiliser ma position actuelle' }));
      const expectedKm = distanceFromRegionCenterKm(
        { lat: 14.7225, lng: -17.4878 },
        TEST_CATALOG.serviceRegion,
      );
      expect(await screen.findByText(/Position trouvée/)).toHaveTextContent(
        `à ${expectedKm} km du centre de la région desservie`,
      );
      // Pas encore appliquée.
      expect(screen.getByText(/Intervention à :/)).toHaveTextContent('Dakar-Plateau');

      fireEvent.click(screen.getByRole('button', { name: 'Utiliser cette position' }));
      expect(screen.getByText(/Intervention à :/)).toHaveTextContent('Ma position actuelle');
      submit();

      await waitFor(() =>
        expect(mockedCreateServiceRequest).toHaveBeenCalledWith(
          expect.objectContaining({
            location: { lat: 14.7225, lng: -17.4878 },
            locationLabel: 'Ma position actuelle',
          }),
        ),
      );
    });

    it('signale une position hors de la région de Dakar et permet de la refuser', async () => {
      mockedGetCurrentPosition.mockResolvedValue({ lat: 48.9097, lng: 2.3819 });
      renderScreen();

      fireEvent.click(screen.getByRole('button', { name: 'Utiliser ma position actuelle' }));
      const found = await screen.findByRole('status');
      expect(within(found).getByText(/hors de la région de Dakar/)).toBeInTheDocument();

      fireEvent.click(within(found).getByRole('button', { name: 'Garder Dakar-Plateau' }));
      expect(screen.queryByText(/Position trouvée/)).not.toBeInTheDocument();
      submit();

      await waitFor(() =>
        expect(mockedCreateServiceRequest).toHaveBeenCalledWith(
          expect.objectContaining({ location: PLATEAU, locationLabel: 'Dakar-Plateau' }),
        ),
      );
    });

    it('dit quand la position est refusée, sans rien remplacer en silence', async () => {
      mockedGetCurrentPosition.mockRejectedValue(new GeolocationError('denied'));
      renderScreen();

      fireEvent.click(screen.getByRole('button', { name: 'Utiliser ma position actuelle' }));

      expect(await screen.findByRole('alert')).toHaveTextContent(
        "L'accès à votre position a été refusé. Choisissez votre quartier dans la liste.",
      );
      expect(screen.getByText(/Intervention à :/)).toHaveTextContent('Dakar-Plateau');
    });

    it("vérifie la zone de l'artisan visé AVANT l'envoi et ne lui envoie rien s'il ne couvre pas le lieu", async () => {
      mockedUseArtisan.mockReturnValue({
        data: { ...artisanFixture, id: 'a1', name: 'Maty Ndiaye', tradeCodes: ['electricite'] },
        isLoading: false,
        error: null,
        reload: vi.fn(),
        setData: vi.fn(),
      });
      mockedCheckCoverage.mockResolvedValue({ eligible: false, reason: 'hors_zone' });
      renderScreen('/demande?artisan=a1');
      describeProblem();

      expect(
        await screen.findByText(/Maty Ndiaye n'intervient pas à Dakar-Plateau/),
      ).toBeInTheDocument();
      expect(mockedCheckCoverage).toHaveBeenCalledWith('a1', 'electricite', PLATEAU);
      expect(
        screen.queryByRole('button', { name: 'Envoyer à Maty Ndiaye' }),
      ).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));
      expect(await screen.findByText(/Search results for/)).toBeInTheDocument();
      expect(mockedCreateIntervention).not.toHaveBeenCalled();
    });

    it('revérifie la zone quand le client change de lieu', async () => {
      mockedUseArtisan.mockReturnValue({
        data: { ...artisanFixture, id: 'a1', name: 'Maty Ndiaye', tradeCodes: ['electricite'] },
        isLoading: false,
        error: null,
        reload: vi.fn(),
        setData: vi.fn(),
      });
      mockedCheckCoverage.mockImplementation(async (_id, _trade, location) =>
        location.lat === PLATEAU.lat
          ? { eligible: false, reason: 'hors_zone' }
          : { eligible: true, reason: null },
      );
      renderScreen('/demande?artisan=a1');
      describeProblem();
      await screen.findByText(/n'intervient pas à Dakar-Plateau/);

      fireEvent.change(screen.getByLabelText('Quartier'), { target: { value: 'ouakam' } });

      expect(await screen.findByRole('button', { name: 'Envoyer à Maty Ndiaye' })).toBeEnabled();
    });
  });
});
