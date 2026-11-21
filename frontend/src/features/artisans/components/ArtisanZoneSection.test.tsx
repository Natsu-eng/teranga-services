import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ApiError, api } from '../../../lib/api';
import { getCurrentPosition } from '../../../lib/geo';
import { TEST_CATALOG } from '../../../testing/neighborhoodCatalog';
import type { ArtisanZone } from '../../../types';
import { PlaceProvider } from '../../location/PlaceProvider';
import { ArtisanZoneCard } from './ArtisanZoneCard';
import { ArtisanZoneSection } from './ArtisanZoneSection';
import { UnplacedBanner } from './UnplacedBanner';

vi.mock('../../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      updateMyArtisanProfile: vi.fn(),
      getMyArtisanZone: vi.fn(),
      updateArtisanTradeRadius: vi.fn(),
    },
  };
});
vi.mock('../../../lib/geo', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/geo')>();
  return { ...actual, getCurrentPosition: vi.fn() };
});

const mockedApi = vi.mocked(api, true);
const mockedGetCurrentPosition = vi.mocked(getCurrentPosition);

function zone(overrides: Partial<ArtisanZone> = {}): ArtisanZone {
  return {
    placed: false,
    source: null,
    neighborhood: null,
    trades: [
      {
        id: 't1',
        tradeCode: 'plomberie',
        tradeLabel: 'Plomberie',
        serviceRadiusM: 10_000,
        hasCustomServiceArea: false,
      },
    ],
    radiusMaxM: 30_000,
    gpsGridM: 500,
    changesRemainingShort: 3,
    changesRemainingLong: 10,
    shortWindowHours: 24,
    longWindowDays: 30,
    nextChangeAt: null,
    ...overrides,
  };
}

const PLACED_IN_MEDINA = zone({
  placed: true,
  source: 'neighborhood',
  neighborhood: { id: 'medina', label: 'Médina', departmentLabel: 'Dakar' },
});

function renderSection(current: ArtisanZone, onZoneChange = vi.fn()) {
  render(
    <PlaceProvider initialCatalog={TEST_CATALOG}>
      <MemoryRouter>
        <ArtisanZoneSection
          zone={current}
          isLoading={false}
          error={null}
          reload={vi.fn()}
          onZoneChange={onZoneChange}
        />
      </MemoryRouter>
    </PlaceProvider>,
  );
  return onZoneChange;
}

describe('ArtisanZoneSection', () => {
  beforeEach(() => {
    mockedApi.updateMyArtisanProfile.mockReset();
    mockedApi.getMyArtisanZone.mockReset();
    mockedApi.updateArtisanTradeRadius.mockReset();
    mockedGetCurrentPosition.mockReset();
  });
  afterEach(cleanup);

  it('dit clairement qu’un artisan non placé ne reçoit aucune demande', () => {
    renderSection(zone());

    expect(screen.getByRole('status')).toHaveTextContent('Vous n’êtes placé nulle part');
    expect(screen.getByRole('status')).toHaveTextContent('vous ne recevez aucune demande');
  });

  it('propose le quartier EN PREMIER, puis le GPS', () => {
    renderSection(zone());

    const choices = within(screen.getByRole('group', { name: 'Comment vous placer' }));
    const buttons = choices.getAllByRole('button');
    expect(buttons.map((button) => button.textContent)).toEqual([
      'Choisir mon quartier',
      'Utiliser ma position GPS',
    ]);
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'true');
  });

  it('place au centre d’un quartier de la liste du serveur, sans aucune coordonnée envoyée', async () => {
    mockedApi.updateMyArtisanProfile.mockImplementation(async () => ({}) as never);
    mockedApi.getMyArtisanZone.mockImplementation(async () => PLACED_IN_MEDINA);
    const onZoneChange = renderSection(zone());

    fireEvent.change(screen.getByLabelText('Mon quartier'), { target: { value: 'medina' } });
    fireEvent.click(screen.getByRole('button', { name: 'Me placer dans ce quartier' }));

    await waitFor(() => expect(onZoneChange).toHaveBeenCalledWith(PLACED_IN_MEDINA));
    expect(mockedApi.updateMyArtisanProfile).toHaveBeenCalledWith({
      location: { source: 'neighborhood', neighborhoodId: 'medina' },
    });
  });

  it('libellés honnêtes : centre du quartier, ou GPS à précision réduite', () => {
    renderSection(PLACED_IN_MEDINA);
    expect(screen.getByRole('status')).toHaveTextContent('Placé au centre de Médina');
    cleanup();

    renderSection(zone({ placed: true, source: 'gps' }));
    expect(screen.getByRole('status')).toHaveTextContent(
      'Placé à votre position GPS (précision réduite)',
    );
  });

  it('GPS : demandé sur clic seulement, arrondi annoncé, envoyé tel quel au serveur', async () => {
    mockedGetCurrentPosition.mockImplementation(async () => ({ lat: 14.6901, lng: -17.4512 }));
    mockedApi.updateMyArtisanProfile.mockImplementation(async () => ({}) as never);
    mockedApi.getMyArtisanZone.mockImplementation(async () =>
      zone({ placed: true, source: 'gps' }),
    );
    renderSection(zone());

    fireEvent.click(screen.getByRole('button', { name: 'Utiliser ma position GPS' }));
    expect(mockedGetCurrentPosition).not.toHaveBeenCalled();
    expect(screen.getByText(/arrondie à environ 500 m/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Me placer à ma position GPS' }));

    await waitFor(() =>
      expect(mockedApi.updateMyArtisanProfile).toHaveBeenCalledWith({
        location: { source: 'gps', lat: 14.6901, lng: -17.4512 },
      }),
    );
  });

  it('affiche le refus du serveur (limite atteinte) et dit que rien n’a changé', async () => {
    mockedApi.updateMyArtisanProfile.mockImplementation(async () => {
      throw new ApiError(
        'validation',
        'Vous avez déjà changé votre zone d’intervention 3 fois en 24 h.',
      );
    });
    const onZoneChange = renderSection(PLACED_IN_MEDINA);

    fireEvent.change(screen.getByLabelText('Mon quartier'), { target: { value: 'yoff' } });
    fireEvent.click(screen.getByRole('button', { name: 'Me placer dans ce quartier' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('3 fois en 24 h');
    expect(alert).toHaveTextContent(/Votre zone enregistrée n'a pas changé/);
    expect(onZoneChange).not.toHaveBeenCalled();
  });

  it('change le rayon d’un métier sans le retirer, plafonné au maximum du serveur', async () => {
    const updated = zone({
      trades: [{ ...zone().trades[0], serviceRadiusM: 12_000 }],
    });
    mockedApi.updateArtisanTradeRadius.mockImplementation(async () => updated);
    const onZoneChange = renderSection(zone());

    fireEvent.click(screen.getByRole('button', { name: /Modifier le rayon/ }));
    const input = screen.getByLabelText('Rayon pour Plomberie (km)');
    fireEvent.change(input, { target: { value: '31' } });
    expect(screen.getByRole('button', { name: 'Enregistrer' })).toBeDisabled();
    fireEvent.change(input, { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));

    await waitFor(() => expect(onZoneChange).toHaveBeenCalledWith(updated));
    expect(mockedApi.updateArtisanTradeRadius).toHaveBeenCalledWith('t1', 12_000);
  });

  it('annonce les changements restants, ou la date de reprise', () => {
    renderSection({ ...PLACED_IN_MEDINA, changesRemainingShort: 2, changesRemainingLong: 9 });
    expect(screen.getByRole('status')).toHaveTextContent('2 sur 24 h, 9 sur 30 jours');
    cleanup();

    renderSection({
      ...PLACED_IN_MEDINA,
      changesRemainingShort: 0,
      nextChangeAt: '2026-11-22T10:00:00Z',
    });
    expect(screen.getByRole('status')).toHaveTextContent('prochain changement possible le');
  });
});

describe('Carte de zone du profil Pro et bandeau du tableau de bord', () => {
  beforeEach(() => mockedApi.getMyArtisanZone.mockReset());
  afterEach(cleanup);

  it('la carte montre la source, le rayon par métier, les changements et Modifier', async () => {
    mockedApi.getMyArtisanZone.mockImplementation(async () => PLACED_IN_MEDINA);
    render(
      <MemoryRouter>
        <ArtisanZoneCard enabled />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Placé au centre de Médina')).toBeInTheDocument();
    expect(screen.getByText('Plomberie')).toBeInTheDocument();
    expect(screen.getByText('rayon 10 km')).toBeInTheDocument();
    expect(screen.getByText(/Changements encore possibles : 3 sur 24 h/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Modifier' })).toHaveAttribute(
      'href',
      '/pro/onboarding#zone',
    );
  });

  it('le bandeau alerte un artisan non placé, avec un lien de correction', async () => {
    mockedApi.getMyArtisanZone.mockImplementation(async () => zone());
    render(
      <MemoryRouter>
        <UnplacedBanner enabled />
      </MemoryRouter>,
    );

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Vous n’êtes placé nulle part : vous ne recevez aucune demande',
    );
    expect(within(alert).getByRole('link')).toHaveAttribute('href', '/pro/onboarding#zone');
  });

  it('aucun bandeau pour un artisan placé', async () => {
    mockedApi.getMyArtisanZone.mockImplementation(async () => PLACED_IN_MEDINA);
    render(
      <MemoryRouter>
        <UnplacedBanner enabled />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockedApi.getMyArtisanZone).toHaveBeenCalled());
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
