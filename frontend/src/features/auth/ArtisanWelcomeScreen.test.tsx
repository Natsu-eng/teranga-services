import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ArtisanWelcomeScreen } from './ArtisanWelcomeScreen';

function renderArtisanWelcomeScreen() {
  return render(
    <MemoryRouter initialEntries={['/bienvenue-artisan']}>
      <Routes>
        <Route path="/bienvenue-artisan" element={<ArtisanWelcomeScreen />} />
        <Route path="/pro/onboarding" element={<div>Artisan onboarding screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ArtisanWelcomeScreen', () => {
  afterEach(cleanup);

  it('renders the welcome message and links to the onboarding screen', async () => {
    renderArtisanWelcomeScreen();

    expect(screen.getByText('Bienvenue chez Téranga Pro !')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Compléter mon profil' }));

    expect(await screen.findByText('Artisan onboarding screen')).toBeInTheDocument();
  });
});
