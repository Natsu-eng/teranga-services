import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { OtpScreen } from './OtpScreen';
import { useAuth } from './hooks/useAuth';
import { ApiError } from '../../lib/api';
import type { AuthContextValue } from './auth-context';

vi.mock('./hooks/useAuth');

const mockedUseAuth = vi.mocked(useAuth);

function renderOtpScreen(state: unknown = { phone: '+221771234501', intent: 'login' }) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/connexion/code', state }]}>
      <Routes>
        <Route path="/connexion" element={<div>Auth entry screen</div>} />
        <Route path="/connexion/code" element={<OtpScreen />} />
        <Route path="/profil" element={<div>Profile screen</div>} />
        <Route path="/artisans/:id" element={<div>Return destination</div>} />
        <Route path="/bienvenue-artisan" element={<div>Artisan welcome screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('OtpScreen', () => {
  const login = vi.fn();
  const signup = vi.fn();
  const requestOtp = vi.fn();

  beforeEach(() => {
    login.mockReset();
    signup.mockReset();
    requestOtp.mockReset();
    mockedUseAuth.mockReturnValue({
      user: null,
      role: null,
      isAuthenticated: false,
      isLoading: false,
      requestOtp,
      login,
      signup,
      logout: vi.fn(),
      updateFullName: vi.fn(),
    } satisfies AuthContextValue);
  });

  afterEach(cleanup);

  it('redirects back to /connexion when reached without a phone in navigation state', async () => {
    renderOtpScreen(null);

    expect(await screen.findByText('Auth entry screen')).toBeInTheDocument();
  });

  it('redirects back to /connexion when reached without an intent in navigation state', async () => {
    renderOtpScreen({ phone: '+221771234501' });

    expect(await screen.findByText('Auth entry screen')).toBeInTheDocument();
  });

  it('rejects a code that is not 6 digits, without calling login or signup', () => {
    renderOtpScreen();

    fireEvent.change(screen.getByPlaceholderText('123456'), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }));

    expect(screen.getByText('Le code doit contenir 6 chiffres.')).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
    expect(signup).not.toHaveBeenCalled();
  });

  it('logs in (intent=login) and navigates to /profil by default on a valid code', async () => {
    login.mockResolvedValue(undefined);
    renderOtpScreen({ phone: '+221771234501', intent: 'login' });

    fireEvent.change(screen.getByPlaceholderText('123456'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }));

    expect(await screen.findByText('Profile screen')).toBeInTheDocument();
    expect(login).toHaveBeenCalledWith('+221771234501', '123456');
    expect(signup).not.toHaveBeenCalled();
  });

  it('signs up a client (intent=signup, role=client) and navigates to /profil by default', async () => {
    signup.mockResolvedValue(undefined);
    renderOtpScreen({
      phone: '+221771234501',
      intent: 'signup',
      role: 'client',
      fullName: 'Fatou Sarr',
    });

    fireEvent.change(screen.getByPlaceholderText('123456'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }));

    expect(await screen.findByText('Profile screen')).toBeInTheDocument();
    expect(signup).toHaveBeenCalledWith('+221771234501', '123456', 'client', 'Fatou Sarr');
    expect(login).not.toHaveBeenCalled();
  });

  it('signs up an artisan (intent=signup, role=artisan) and navigates to the welcome screen', async () => {
    signup.mockResolvedValue(undefined);
    renderOtpScreen({
      phone: '+221771234501',
      intent: 'signup',
      role: 'artisan',
      fullName: 'Idrissa Diop',
    });

    fireEvent.change(screen.getByPlaceholderText('123456'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }));

    expect(await screen.findByText('Artisan welcome screen')).toBeInTheDocument();
    expect(signup).toHaveBeenCalledWith('+221771234501', '123456', 'artisan', 'Idrissa Diop');
  });

  it('returns to the originating page (from) after login when the phone step carried one', async () => {
    login.mockResolvedValue(undefined);
    renderOtpScreen({
      phone: '+221771234501',
      intent: 'login',
      from: { pathname: '/artisans/idrissa-diop' },
    });

    fireEvent.change(screen.getByPlaceholderText('123456'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }));

    expect(await screen.findByText('Return destination')).toBeInTheDocument();
  });

  it("shows the backend's error message as-is on an invalid code", async () => {
    login.mockRejectedValue(new ApiError('validation', 'Code invalide.'));
    renderOtpScreen();

    fireEvent.change(screen.getByPlaceholderText('123456'), { target: { value: '000000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }));

    expect(await screen.findByText('Code invalide.')).toBeInTheDocument();
  });

  it("shows the backend's error message as-is when signing up on an already-registered phone", async () => {
    signup.mockRejectedValue(
      new ApiError('validation', 'Un compte existe déjà avec ce numéro. Connectez-vous.'),
    );
    renderOtpScreen({ phone: '+221771234501', intent: 'signup', role: 'client' });

    fireEvent.change(screen.getByPlaceholderText('123456'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }));

    expect(
      await screen.findByText('Un compte existe déjà avec ce numéro. Connectez-vous.'),
    ).toBeInTheDocument();
  });

  it("shows the backend's error message as-is when logging in on a nonexistent phone", async () => {
    login.mockRejectedValue(new ApiError('not_found', 'Aucun compte pour ce numéro. Inscrivez-vous.'));
    renderOtpScreen({ phone: '+221771234501', intent: 'login' });

    fireEvent.change(screen.getByPlaceholderText('123456'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }));

    expect(await screen.findByText('Aucun compte pour ce numéro. Inscrivez-vous.')).toBeInTheDocument();
  });

  it('disables resend until the delay elapses, then allows requesting a new code', () => {
    vi.useFakeTimers();
    try {
      renderOtpScreen();

      expect(screen.getByRole('button', { name: /Renvoyer le code/ })).toBeDisabled();

      // Advance one second at a time: each tick's setState only schedules
      // the next setTimeout once React re-renders, so a single large
      // advanceTimersByTime wouldn't unwind the whole chain.
      for (let i = 0; i < 30; i += 1) {
        act(() => {
          vi.advanceTimersByTime(1000);
        });
      }

      expect(screen.getByRole('button', { name: 'Renvoyer le code' })).not.toBeDisabled();
    } finally {
      vi.useRealTimers();
    }
  });
});
