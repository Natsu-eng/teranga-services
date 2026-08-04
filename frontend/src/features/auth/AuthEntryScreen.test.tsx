import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { AuthEntryScreen } from './AuthEntryScreen';

function StateProbe({ label }: { label: string }) {
  const location = useLocation();
  return <div>{`${label}: ${JSON.stringify(location.state)}`}</div>;
}

function renderAuthEntryScreen(state: unknown = null) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/connexion', state }]}>
      <Routes>
        <Route path="/connexion" element={<AuthEntryScreen />} />
        <Route path="/connexion/role" element={<StateProbe label="Role select screen" />} />
        <Route path="/connexion/telephone" element={<StateProbe label="Phone screen" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AuthEntryScreen', () => {
  afterEach(cleanup);

  it('navigates to the phone step with intent=login on "Se connecter"', async () => {
    renderAuthEntryScreen({ from: { pathname: '/artisans/idrissa-diop' } });

    fireEvent.click(screen.getByRole('button', { name: 'Se connecter' }));

    expect(
      await screen.findByText(
        'Phone screen: {"intent":"login","from":{"pathname":"/artisans/idrissa-diop"}}',
      ),
    ).toBeInTheDocument();
  });

  it('navigates to the role selection screen (no intent yet) on "Créer un compte"', async () => {
    renderAuthEntryScreen();

    fireEvent.click(screen.getByRole('button', { name: 'Créer un compte' }));

    expect(await screen.findByText('Role select screen: {}')).toBeInTheDocument();
  });
});
