import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { NameScreen } from './NameScreen';

function StateProbe({ label }: { label: string }) {
  const location = useLocation();
  return <div>{`${label}: ${JSON.stringify(location.state)}`}</div>;
}

function renderNameScreen(state: unknown = { intent: 'signup', role: 'client' }) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/connexion/nom', state }]}>
      <Routes>
        <Route path="/connexion" element={<div>Auth entry screen</div>} />
        <Route path="/connexion/nom" element={<NameScreen />} />
        <Route path="/connexion/telephone" element={<StateProbe label="Phone screen" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('NameScreen', () => {
  afterEach(cleanup);

  it('redirects back to /connexion when reached without intent=signup in navigation state', async () => {
    renderNameScreen(null);

    expect(await screen.findByText('Auth entry screen')).toBeInTheDocument();
  });

  it('redirects back to /connexion when reached without a role in navigation state', async () => {
    renderNameScreen({ intent: 'signup' });

    expect(await screen.findByText('Auth entry screen')).toBeInTheDocument();
  });

  it('redirects back to /connexion when reached with intent=login', async () => {
    renderNameScreen({ intent: 'login', role: 'client' });

    expect(await screen.findByText('Auth entry screen')).toBeInTheDocument();
  });

  it('rejects a blank name without navigating', () => {
    renderNameScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Continuer' }));

    expect(screen.getByText('Le nom est requis (au moins 2 caractères).')).toBeInTheDocument();
  });

  it('rejects a single-character name without navigating', () => {
    renderNameScreen();

    fireEvent.change(screen.getByPlaceholderText('Ex. Idrissa Diop'), { target: { value: 'A' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continuer' }));

    expect(screen.getByText('Le nom est requis (au moins 2 caractères).')).toBeInTheDocument();
  });

  it('trims the name and carries intent/role/fullName/from forward to the phone screen', async () => {
    renderNameScreen({ intent: 'signup', role: 'client', from: { pathname: '/demande' } });

    fireEvent.change(screen.getByPlaceholderText('Ex. Idrissa Diop'), {
      target: { value: '  Fatou Sarr  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continuer' }));

    expect(
      await screen.findByText(
        'Phone screen: {"intent":"signup","role":"client","fullName":"Fatou Sarr","from":{"pathname":"/demande"}}',
      ),
    ).toBeInTheDocument();
  });

  it('shows role-specific copy for artisan vs client', () => {
    renderNameScreen({ intent: 'signup', role: 'artisan' });

    expect(
      screen.getByText('Ce nom sera affiché sur votre fiche publique, visible par les clients.'),
    ).toBeInTheDocument();
  });
});
