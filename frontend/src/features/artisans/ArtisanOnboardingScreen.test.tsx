import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ArtisanOnboardingScreen } from './ArtisanOnboardingScreen';
import { useAuth } from '../auth/hooks/useAuth';
import { useCurrentUser } from '../profile/hooks/useCurrentUser';
import { ApiError, api } from '../../lib/api';
import type { AuthContextValue } from '../auth/auth-context';
import type { MyArtisanProfile, MyVerification, Trade } from '../../types';

vi.mock('../auth/hooks/useAuth');
vi.mock('../profile/hooks/useCurrentUser');
vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getMyArtisanProfile: vi.fn(),
      updateMyArtisanProfile: vi.fn(),
      addArtisanTrade: vi.fn(),
      removeArtisanTrade: vi.fn(),
      listMyVerificationDocuments: vi.fn(),
      uploadVerificationDocument: vi.fn(),
      listTrades: vi.fn(),
    },
  };
});

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseCurrentUser = vi.mocked(useCurrentUser);
const mockedApi = vi.mocked(api, true);

function authValue(overrides: Partial<AuthContextValue>): AuthContextValue {
  return {
    user: null,
    role: null,
    isAuthenticated: true,
    isLoading: false,
    requestOtp: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

const profileFixture: MyArtisanProfile = {
  id: 'artisan-1',
  fullName: 'Idrissa Diop',
  bio: 'Plombier expérimenté.',
  yearsExperience: 8,
  avatarUrl: null,
  isAvailable: true,
  verifiedStatus: 'none',
  trades: [],
};

const verificationFixture: MyVerification = {
  verifiedStatus: 'none',
  documents: [],
};

const tradesFixture: Trade[] = [
  { id: 't1', code: 'plomberie', labelFr: 'Plomberie' },
  { id: 't2', code: 'electricite', labelFr: 'Électricité' },
];

function renderScreen() {
  return render(
    <MemoryRouter>
      <ArtisanOnboardingScreen />
    </MemoryRouter>,
  );
}

describe('ArtisanOnboardingScreen', () => {
  beforeEach(() => {
    mockedUseCurrentUser.mockReturnValue({
      data: {
        id: 'user-1',
        name: 'Idrissa Diop',
        initials: 'ID',
        verified: true,
        artisanId: 'artisan-1',
      },
      isLoading: false,
      error: null,
      reload: vi.fn(),
    });
    mockedUseAuth.mockReturnValue(authValue({ role: 'artisan' }));
    mockedApi.getMyArtisanProfile.mockReset().mockResolvedValue(profileFixture);
    mockedApi.listMyVerificationDocuments.mockReset().mockResolvedValue(verificationFixture);
    mockedApi.listTrades.mockReset().mockResolvedValue(tradesFixture);
    mockedApi.updateMyArtisanProfile.mockReset();
    mockedApi.addArtisanTrade.mockReset();
    mockedApi.removeArtisanTrade.mockReset();
    mockedApi.uploadVerificationDocument.mockReset();
  });

  afterEach(cleanup);

  it('shows an honest "reserved for artisans" message for a client', () => {
    mockedUseAuth.mockReturnValue(authValue({ role: 'client' }));

    renderScreen();

    expect(screen.getByText('Cet espace est réservé aux artisans.')).toBeInTheDocument();
    expect(mockedApi.getMyArtisanProfile).not.toHaveBeenCalled();
  });

  it('pre-fills the profile form from the fetched profile', async () => {
    renderScreen();

    expect(await screen.findByDisplayValue('Plombier expérimenté.')).toBeInTheDocument();
    expect(screen.getByDisplayValue('8')).toBeInTheDocument();
  });

  it('shows the "none" status banner and an incomplete checklist before anything is submitted', async () => {
    renderScreen();

    expect(
      await screen.findByText('Complétez votre profil pour démarrer la vérification'),
    ).toBeInTheDocument();
    expect(screen.getByText('Vérification en attente')).toBeInTheDocument();
  });

  it('saves the profile with the edited fields and reflects the update', async () => {
    mockedApi.updateMyArtisanProfile.mockResolvedValue({
      ...profileFixture,
      bio: 'Nouvelle bio soignée.',
      yearsExperience: 10,
    });

    renderScreen();

    const bioInput = await screen.findByDisplayValue('Plombier expérimenté.');
    fireEvent.change(bioInput, { target: { value: 'Nouvelle bio soignée.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer mon profil' }));

    await waitFor(() =>
      expect(mockedApi.updateMyArtisanProfile).toHaveBeenCalledWith(
        expect.objectContaining({ bio: 'Nouvelle bio soignée.', yearsExperience: 8 }),
      ),
    );
    expect(await screen.findByDisplayValue('Nouvelle bio soignée.')).toBeInTheDocument();
  });

  it('adds a declared trade and shows it in the list', async () => {
    mockedApi.addArtisanTrade.mockResolvedValue({
      ...profileFixture,
      trades: [
        {
          id: 'at-1',
          tradeCode: 'plomberie',
          tradeLabel: 'Plomberie',
          hourlyRateFcfa: 15000,
          serviceRadiusM: 5000,
          hasCustomServiceArea: false,
        },
      ],
    });

    renderScreen();

    await screen.findByText('Choisir un métier');
    fireEvent.change(screen.getByDisplayValue('Choisir un métier'), {
      target: { value: 'plomberie' },
    });
    fireEvent.change(screen.getByPlaceholderText('Tarif horaire (FCFA)'), {
      target: { value: '15000' },
    });
    fireEvent.change(screen.getByPlaceholderText('Rayon (km)'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: /Ajouter ce métier/ }));

    await waitFor(() =>
      expect(mockedApi.addArtisanTrade).toHaveBeenCalledWith({
        tradeCode: 'plomberie',
        hourlyRateFcfa: 15000,
        serviceRadiusM: 5000,
      }),
    );
    expect(await screen.findByText('Plomberie')).toBeInTheDocument();
    expect(screen.getByText(/15 000 FCFA\/h/)).toBeInTheDocument();
  });

  it('removes a declared trade', async () => {
    mockedApi.getMyArtisanProfile.mockResolvedValue({
      ...profileFixture,
      trades: [
        {
          id: 'at-1',
          tradeCode: 'plomberie',
          tradeLabel: 'Plomberie',
          hourlyRateFcfa: 15000,
          serviceRadiusM: 5000,
          hasCustomServiceArea: false,
        },
      ],
    });
    mockedApi.removeArtisanTrade.mockResolvedValue({ ...profileFixture, trades: [] });

    renderScreen();

    const removeButton = await screen.findByRole('button', { name: 'Retirer Plomberie' });
    fireEvent.click(removeButton);

    await waitFor(() => expect(mockedApi.removeArtisanTrade).toHaveBeenCalledWith('at-1'));
    // "Plomberie" réapparaît légitimement comme option du select "ajouter un
    // métier" une fois qu'elle n'est plus déclarée -- c'est l'élément de
    // liste (avec son bouton de retrait) qui doit disparaître, pas chaque
    // occurrence du mot.
    expect(screen.queryByRole('button', { name: 'Retirer Plomberie' })).not.toBeInTheDocument();
  });

  it('uploads a document and refreshes the verification status', async () => {
    mockedApi.uploadVerificationDocument.mockResolvedValue({
      id: 'doc-1',
      docType: 'cni',
      status: 'pending',
      note: null,
      createdAt: '2026-01-01T00:00:00Z',
      reviewedAt: null,
    });
    mockedApi.listMyVerificationDocuments
      .mockResolvedValueOnce(verificationFixture)
      .mockResolvedValueOnce({
        verifiedStatus: 'pending',
        documents: [
          {
            id: 'doc-1',
            docType: 'cni',
            status: 'pending',
            note: null,
            createdAt: '2026-01-01T00:00:00Z',
            reviewedAt: null,
          },
        ],
      });

    const { container } = renderScreen();

    await screen.findByText("Carte d'identité (CNI)");
    // REQUIRED_DOCS affiche la CNI avant le selfie -- le premier input
    // fichier caché de la page est toujours celui de la CNI.
    const [cniInput] = container.querySelectorAll<HTMLInputElement>('input[type="file"]');
    const file = new File(['fake-bytes'], 'cni.jpg', { type: 'image/jpeg' });
    fireEvent.change(cniInput, { target: { files: [file] } });

    await waitFor(() =>
      expect(mockedApi.uploadVerificationDocument).toHaveBeenCalledWith('cni', file),
    );
    expect(await screen.findByText('En attente de revue')).toBeInTheDocument();
    expect(mockedApi.listMyVerificationDocuments).toHaveBeenCalledTimes(2);
  });

  it('shows an inline error when the upload is rejected (e.g. falsified file type)', async () => {
    mockedApi.uploadVerificationDocument.mockRejectedValue(
      new ApiError('validation', "Le fichier fourni n'est pas d'un type accepté pour ce document."),
    );

    const { container } = renderScreen();

    await screen.findByText("Carte d'identité (CNI)");
    const [cniInput] = container.querySelectorAll<HTMLInputElement>('input[type="file"]');
    const file = new File(['fake-bytes'], 'cni.jpg', { type: 'image/jpeg' });
    fireEvent.change(cniInput, { target: { files: [file] } });

    expect(
      await screen.findByText("Le fichier fourni n'est pas d'un type accepté pour ce document."),
    ).toBeInTheDocument();
  });
});
