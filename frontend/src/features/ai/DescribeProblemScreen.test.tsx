import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router';
import { DescribeProblemScreen } from './DescribeProblemScreen';
import { useArtisans } from '../artisans/hooks/useArtisans';
import { useAnalyzeProblem } from './hooks/useAnalyzeProblem';
import { useAuth } from '../auth/hooks/useAuth';
import { getCurrentPosition } from '../../lib/geo';
import { api, ApiError } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { AIAnalysisResult, Artisan, ServiceRequest } from '../../types';

vi.mock('../artisans/hooks/useArtisans');
vi.mock('./hooks/useAnalyzeProblem');
vi.mock('../auth/hooks/useAuth');
vi.mock('../../lib/geo');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return { ...actual, api: { ...actual.api, createServiceRequest: vi.fn() } };
});

const mockedUseArtisans = vi.mocked(useArtisans);
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

function renderScreen() {
  return render(
    <MemoryRouter initialEntries={['/demande']}>
      <Routes>
        <Route path="/demande" element={<DescribeProblemScreen />} />
        <Route path="/connexion" element={<div>Login screen</div>} />
        <Route path="/recherche" element={<SearchParamsProbe />} />
      </Routes>
    </MemoryRouter>,
  );
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
  });

  afterEach(cleanup);

  it('creates a service request with the AI-detected trade code and lands on a server-filtered search', async () => {
    mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true }));

    renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));

    await waitFor(() => expect(mockedCreateServiceRequest).toHaveBeenCalledTimes(1));
    expect(mockedCreateServiceRequest).toHaveBeenCalledWith(
      expect.objectContaining({
        tradeCode: 'electricite',
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
    fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));

    expect(await screen.findByText('Login screen')).toBeInTheDocument();
    expect(mockedCreateServiceRequest).not.toHaveBeenCalled();
  });

  it("shows the backend's error message when request creation fails", async () => {
    mockedUseAuth.mockReturnValue(authValue({ isAuthenticated: true }));
    mockedCreateServiceRequest.mockRejectedValue(
      new ApiError('validation', "Le métier demandé est introuvable ou inactif."),
    );

    renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Voir les artisans/ }));

    expect(await screen.findByText('Le métier demandé est introuvable ou inactif.')).toBeInTheDocument();
  });
});
