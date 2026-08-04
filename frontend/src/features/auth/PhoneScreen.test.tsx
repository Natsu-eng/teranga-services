import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { PhoneScreen } from './PhoneScreen';
import { useAuth } from './hooks/useAuth';
import { ApiError } from '../../lib/api';
import type { AuthContextValue } from './auth-context';

vi.mock('./hooks/useAuth');

const mockedUseAuth = vi.mocked(useAuth);

function renderPhoneScreen(state: unknown = { intent: 'login' }) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/connexion/telephone', state }]}>
      <Routes>
        <Route path="/connexion" element={<div>Auth entry screen</div>} />
        <Route path="/connexion/telephone" element={<PhoneScreen />} />
        <Route path="/connexion/code" element={<div>OTP screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('PhoneScreen', () => {
  const requestOtp = vi.fn();

  beforeEach(() => {
    requestOtp.mockReset();
    mockedUseAuth.mockReturnValue({
      user: null,
      role: null,
      isAuthenticated: false,
      isLoading: false,
      requestOtp,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
    } satisfies AuthContextValue);
  });

  afterEach(cleanup);

  it('redirects back to /connexion when reached without an intent in navigation state', async () => {
    renderPhoneScreen(null);

    expect(await screen.findByText('Auth entry screen')).toBeInTheDocument();
  });

  it('rejects an obviously malformed phone number without calling the backend', () => {
    renderPhoneScreen();

    fireEvent.change(screen.getByPlaceholderText('+221771234567'), { target: { value: '0771234567' } });
    fireEvent.click(screen.getByRole('button', { name: 'Recevoir le code' }));

    expect(screen.getByText(/Numéro invalide/)).toBeInTheDocument();
    expect(requestOtp).not.toHaveBeenCalled();
  });

  it('requests an OTP and navigates to the code screen on a valid phone, carrying the intent forward', async () => {
    requestOtp.mockResolvedValue(undefined);
    renderPhoneScreen({ intent: 'login' });

    fireEvent.change(screen.getByPlaceholderText('+221771234567'), { target: { value: '+221771234501' } });
    fireEvent.click(screen.getByRole('button', { name: 'Recevoir le code' }));

    expect(await screen.findByText('OTP screen')).toBeInTheDocument();
    expect(requestOtp).toHaveBeenCalledWith('+221771234501');
  });

  it('shows the signup copy and carries the chosen role forward when reached with intent=signup', async () => {
    requestOtp.mockResolvedValue(undefined);
    renderPhoneScreen({ intent: 'signup', role: 'artisan' });

    expect(screen.getByText('Créer votre compte')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('+221771234567'), { target: { value: '+221771234501' } });
    fireEvent.click(screen.getByRole('button', { name: 'Recevoir le code' }));

    expect(await screen.findByText('OTP screen')).toBeInTheDocument();
  });

  it("shows the backend's error message as-is when request-otp fails", async () => {
    requestOtp.mockRejectedValue(new ApiError('validation', 'Trop de demandes, merci de réessayer plus tard.'));
    renderPhoneScreen();

    fireEvent.change(screen.getByPlaceholderText('+221771234567'), { target: { value: '+221771234501' } });
    fireEvent.click(screen.getByRole('button', { name: 'Recevoir le code' }));

    expect(await screen.findByText('Trop de demandes, merci de réessayer plus tard.')).toBeInTheDocument();
  });
});
