import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { AppBar } from './AppBar';

afterEach(() => {
  cleanup();
  window.history.replaceState(null, '');
});

function renderAt(entries: string[], initialIndex: number, appBar: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={entries} initialIndex={initialIndex}>
      <Routes>
        <Route path="/accueil" element={<div>Accueil</div>} />
        <Route path="/recherche" element={<div>Recherche</div>} />
        <Route path="/artisans/1" element={appBar} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AppBar', () => {
  it('affiche le titre de la page en h1', () => {
    renderAt(['/artisans/1'], 0, <AppBar title="Profil artisan" />);

    expect(screen.getByRole('heading', { level: 1, name: 'Profil artisan' })).toBeInTheDocument();
  });

  it('revient à la page précédente de l’app quand elle existe', () => {
    // React Router mémorise la position dans history.state.idx.
    window.history.replaceState({ idx: 1 }, '');
    renderAt(['/recherche', '/artisans/1'], 1, <AppBar title="Profil artisan" backTo="/accueil" />);

    fireEvent.click(screen.getByRole('button', { name: 'Retour' }));

    expect(screen.getByText('Recherche')).toBeInTheDocument();
  });

  it('va à la destination de repli sur un lien profond (aucune page précédente dans l’app)', () => {
    renderAt(['/artisans/1'], 0, <AppBar title="Profil artisan" backTo="/accueil" />);

    fireEvent.click(screen.getByRole('button', { name: 'Retour' }));

    expect(screen.getByText('Accueil')).toBeInTheDocument();
  });

  it('délègue entièrement le retour quand onBack est fourni', () => {
    const onBack = vi.fn();
    renderAt(['/artisans/1'], 0, <AppBar title="Profil artisan" onBack={onBack} />);

    fireEvent.click(screen.getByRole('button', { name: 'Retour' }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('prend la tonalité vert profond de l’espace Pro', () => {
    renderAt(['/artisans/1'], 0, <AppBar title="Mon profil Pro" tone="pro" />);

    const header = screen.getByRole('banner');
    expect(header).toHaveAttribute('data-tone', 'dark');
    expect(header.className).toContain('bg-primary');
  });
});
