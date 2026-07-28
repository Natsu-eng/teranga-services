import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { RoleSelectScreen } from './RoleSelectScreen';

function StateProbe({ label }: { label: string }) {
  const location = useLocation();
  return <div>{`${label}: ${JSON.stringify(location.state)}`}</div>;
}

function renderRoleSelectScreen(state: unknown = null) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/connexion/role', state }]}>
      <Routes>
        <Route path="/connexion" element={<div>Auth entry screen</div>} />
        <Route path="/connexion/role" element={<RoleSelectScreen />} />
        <Route path="/connexion/telephone" element={<StateProbe label="Phone screen" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RoleSelectScreen', () => {
  afterEach(cleanup);

  it('carries intent=signup and role=client forward when picking "Je cherche un artisan"', async () => {
    renderRoleSelectScreen({ from: { pathname: '/demande' } });

    fireEvent.click(screen.getByRole('button', { name: /Je cherche un artisan/ }));

    expect(
      await screen.findByText(
        'Phone screen: {"intent":"signup","role":"client","from":{"pathname":"/demande"}}',
      ),
    ).toBeInTheDocument();
  });

  it('carries intent=signup and role=artisan forward when picking "Je suis un artisan"', async () => {
    renderRoleSelectScreen();

    fireEvent.click(screen.getByRole('button', { name: /Je suis un artisan/ }));

    expect(
      await screen.findByText('Phone screen: {"intent":"signup","role":"artisan"}'),
    ).toBeInTheDocument();
  });

  it('navigates back to /connexion on "Retour"', async () => {
    renderRoleSelectScreen();

    fireEvent.click(screen.getByRole('button', { name: /Retour/ }));

    expect(await screen.findByText('Auth entry screen')).toBeInTheDocument();
  });
});
