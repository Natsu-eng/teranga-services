import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ArtisanWelcomeScreen } from './ArtisanWelcomeScreen';

function renderArtisanWelcomeScreen() {
  return render(
    <MemoryRouter initialEntries={['/bienvenue-artisan']}>
      <Routes>
        <Route path="/bienvenue-artisan" element={<ArtisanWelcomeScreen />} />
        <Route path="/pro" element={<div>Artisan dashboard screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ArtisanWelcomeScreen', () => {
  afterEach(cleanup);

  it('renders the welcome message and links to the artisan dashboard', async () => {
    renderArtisanWelcomeScreen();

    expect(screen.getByText('Bienvenue chez Téranga Pro !')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Accéder à mon tableau de bord' }));

    expect(await screen.findByText('Artisan dashboard screen')).toBeInTheDocument();
  });
});
