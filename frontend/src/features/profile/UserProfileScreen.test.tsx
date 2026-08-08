import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { UserProfileScreen } from './UserProfileScreen';
import { useAuth } from '../auth/hooks/useAuth';
import { useCurrentUser } from './hooks/useCurrentUser';
import { ApiError } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';

vi.mock('../auth/hooks/useAuth');
vi.mock('./hooks/useCurrentUser');

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseCurrentUser = vi.mocked(useCurrentUser);

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

function renderScreen() {
  return render(
    <MemoryRouter>
      <UserProfileScreen location="Dakar Plateau" />
    </MemoryRouter>,
  );
}

describe('UserProfileScreen', () => {
  const updateFullName = vi.fn();

  beforeEach(() => {
    updateFullName.mockReset();
    mockedUseAuth.mockReturnValue(authValue({ role: 'client', updateFullName }));
    mockedUseCurrentUser.mockReturnValue({
      data: {
        id: 'user-1',
        name: 'Diandé Diallo',
        initials: 'DD',
        verified: true,
        artisanId: null,
      },
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });
  });

  afterEach(cleanup);

  it('shows the current name with no edit input visible', () => {
    renderScreen();

    expect(screen.getByText('Diandé Diallo')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Enregistrer' })).not.toBeInTheDocument();
  });

  it('opens an edit input pre-filled with the current name on clicking the pencil', () => {
    renderScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Modifier mon nom' }));

    expect(screen.getByDisplayValue('Diandé Diallo')).toBeInTheDocument();
  });

  it('saves the edited name and returns to display mode', async () => {
    updateFullName.mockResolvedValue(undefined);
    renderScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Modifier mon nom' }));
    const input = screen.getByDisplayValue('Diandé Diallo');
    fireEvent.change(input, { target: { value: 'Diandé D. Diallo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));

    await waitFor(() => expect(updateFullName).toHaveBeenCalledWith('Diandé D. Diallo'));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Enregistrer' })).not.toBeInTheDocument(),
    );
  });

  it('cancels editing without calling updateFullName', () => {
    renderScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Modifier mon nom' }));
    fireEvent.change(screen.getByDisplayValue('Diandé Diallo'), { target: { value: 'Autre nom' } });
    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }));

    expect(updateFullName).not.toHaveBeenCalled();
    expect(screen.getByText('Diandé Diallo')).toBeInTheDocument();
  });

  it("shows the backend's error message inline when the update is rejected", async () => {
    updateFullName.mockRejectedValue(new ApiError('validation', 'Le nom est requis (au moins 2 caractères).'));
    renderScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Modifier mon nom' }));
    fireEvent.change(screen.getByDisplayValue('Diandé Diallo'), { target: { value: 'A' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));

    expect(
      await screen.findByText('Le nom est requis (au moins 2 caractères).'),
    ).toBeInTheDocument();
  });
});
