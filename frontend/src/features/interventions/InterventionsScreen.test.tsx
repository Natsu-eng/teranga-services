import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { InterventionsScreen } from './InterventionsScreen';
import { useMyInterventions } from './hooks/useMyInterventions';
import { useAuth } from '../auth/hooks/useAuth';
import { ApiError } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { Intervention } from '../../types';

vi.mock('./hooks/useMyInterventions');
vi.mock('../auth/hooks/useAuth');

const mockedUseMyInterventions = vi.mocked(useMyInterventions);
const mockedUseAuth = vi.mocked(useAuth);

function authValue(overrides: Partial<AuthContextValue>): AuthContextValue {
  return {
    user: null,
    role: null,
    isAuthenticated: true,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    updateFullName: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

const interventionFixture: Intervention = {
  id: 'int-1',
  serviceRequest: {
    id: 'req-1',
    tradeCode: 'plomberie',
    tradeLabel: 'Plomberie',
    description: 'Fuite sous l’évier.',
    photoUrl: null,
    location: { lat: 14.6937, lng: -17.4441 },
    urgency: 'normal',
    aiEstimateMinFcfa: null,
    aiEstimateMaxFcfa: null,
    status: 'en_relation',
    createdAt: '2026-01-01T00:00:00Z',
  },
  clientId: 'client-1',
  artisanId: 'artisan-1',
  status: 'proposee',
  commissionRateBps: 1000,
  agreedAmountFcfa: null,
  scheduledAt: null,
  completedAt: null,
  declineReason: null,
  quote: null,
  review: null,
  conversationId: null,
  createdAt: '2026-01-01T00:00:00Z',
};

function renderScreen() {
  return render(
    <MemoryRouter>
      <InterventionsScreen />
    </MemoryRouter>,
  );
}

describe('InterventionsScreen', () => {
  beforeEach(() => {
    mockedUseMyInterventions.mockReset();
  });

  afterEach(cleanup);

  it('shows the client-facing title for a client', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'client' }));
    mockedUseMyInterventions.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.getByText('Devis et travaux')).toBeInTheDocument();
  });

  it('shows the artisan-facing title for an artisan', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));
    mockedUseMyInterventions.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.getByText('Mes demandes reçues')).toBeInTheDocument();
  });

  it('shows a loading skeleton while fetching', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'client' }));
    mockedUseMyInterventions.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
      reload: vi.fn(),
    });

    const { container } = renderScreen();

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('shows an error state with a working retry button', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'client' }));
    const reload = vi.fn();
    mockedUseMyInterventions.mockReturnValue({
      data: null,
      isLoading: false,
      error: new ApiError('network', 'Impossible de charger les interventions.'),
      reload,
    });

    renderScreen();

    expect(screen.getByText('Impossible de charger les interventions.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Réessayer' }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('shows an empty state when there are no interventions', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));
    mockedUseMyInterventions.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.getByText("Aucune demande reçue pour l'instant.")).toBeInTheDocument();
  });

  it('renders one InterventionCard per intervention on success', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'client' }));
    mockedUseMyInterventions.mockReturnValue({
      data: [interventionFixture],
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });

    renderScreen();

    expect(screen.getByText('Plomberie')).toBeInTheDocument();
  });
});
