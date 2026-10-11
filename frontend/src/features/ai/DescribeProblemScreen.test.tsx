import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router';
import { DescribeProblemScreen } from './DescribeProblemScreen';
import { useArtisans } from '../artisans/hooks/useArtisans';
import { useArtisan } from '../artisans/hooks/useArtisan';
import { useAnalyzeProblem } from './hooks/useAnalyzeProblem';
import { useAuth } from '../auth/hooks/useAuth';
import { getCurrentPosition } from '../../lib/geo';
import { api, ApiError } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { AIAnalysisResult, Artisan, Intervention, ServiceRequest } from '../../types';

vi.mock('../artisans/hooks/useArtisans');
vi.mock('../artisans/hooks/useArtisan');
vi.mock('./hooks/useAnalyzeProblem');
vi.mock('../auth/hooks/useAuth');
vi.mock('../../lib/geo');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: { ...actual.api, createServiceRequest: vi.fn(), createIntervention: vi.fn() },
  };
});

const mockedUseArtisans = vi.mocked(useArtisans);
const mockedUseArtisan = vi.mocked(useArtisan);
const mockedCreateIntervention = vi.mocked(api.createIntervention);
const mockedUseAnalyzeProblem = vi.mocked(useAnalyzeProblem);
const mockedUseAuth = vi.mocked(useAuth);
const mockedGetCurrentPosition = vi.mocked(getCurrentPosition);
const mockedCreateServiceRequest = vi.mocked(api.createServiceRequest);

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
  location: 'Dakar, Sénégal',
  priceBase: 'Tarif sur devis',
  priceNumber: 0,
  tags: ['Électricité'],
  tradeCodes: ['electricite'],
  bio: '',
  stats: { chantiers: '5', responseTime: 'Non communiqué', experience: '6 ans' },
  realisations: [],
  reviews: [],
  available: true,
};

const aiResultFixture: AIAnalysisResult = {
  trade: 'Électricité',
  tradeCode: 'electricite',
  priceEstimate: '12 000 – 25 000 FCFA',
  priceMinFcfa: 12_000,
  priceMaxFcfa: 25_000,
  recommendedCount: 3,
  explanation: "L'IA a analysé votre description.",
  urgency: 'haute',
  urgencyCode: 'urgent',
  suggestedDevis: { title: 'Électricité', labor: 15_000, materials: 5_000, total: 20_000 },
};

const serviceRequestFixture: ServiceRequest = {
  id: 'req-1',
  tradeCode: 'electricite',
  tradeLabel: 'Électricité',
  description: 'Une prise ne fonctionne plus.',
  photoUrl: null,
  location: { lat: 1, lng: 2 },
  urgency: 'urgent',
  aiEstimateMinFcfa: 12_000,
  aiEstimateMaxFcfa: 25_000,
  status: 'ouverte',
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
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/demande" element={<DescribeProblemScreen />} />
        <Route path="/connexion" element={<div>Login screen</div>} />
        <Route path="/recherche" element={<SearchParamsProbe />} />
        <Route path="/mes-interventions" element={<div>Mes interventions</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const DESCRIPTION = 'Une prise ne fonctionne plus dans le salon.';

/** Saisit une vraie description : l'envoi exige un texte suffisant. */
function describeProblem(text = DESCRIPTION) {
  fireEvent.change(screen.getByLabelText('Votre problème'), { target: { value: text } });
}

describe('DescribeProblemScreen', () => {
  beforeEach(() => {
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
    mockedGetCurrentPosition.mockResolvedValue({ lat: 1, lng: 2 });
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
        aiEstimateMinFcfa: 12_000,
        aiEstimateMaxFcfa: 25_000,
        location: { lat: 1, lng: 2 },
      }),
    );

    const results = await screen.findByText(/Search results for/);
    expect(results.textContent).toContain('trade=electricite');
    expect(results.textContent).toContain('lat=1');
    expect(results.textContent).toContain('lng=2');
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
      fireEvent.click(screen.getByRole('button', { name: 'Envoyer à Maty Ndiaye' }));

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
      fireEvent.click(screen.getByRole('button', { name: 'Envoyer à Maty Ndiaye' }));

      expect(await screen.findByRole('alert')).toHaveTextContent(
        /n'intervient pas dans votre zone/,
      );
      const fallback = screen.getByRole('link', { name: /Voir les autres artisans/ });
      expect(fallback.getAttribute('href')).toContain('trade=electricite');
      expect(mockedCreateServiceRequest).toHaveBeenCalledTimes(1);
    });
  });
});
