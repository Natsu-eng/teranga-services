import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { api } from '../../lib/api';
import type { PushBrowser } from '../../lib/push/webPush';
import { enablePushNotifications } from '../../lib/push/webPush';
import { PUSH_PROMPT_DISMISSED_KEY, PushNotificationsPrompt } from './PushNotificationsPrompt';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return { ...actual, api: { ...actual.api, getPushConfig: vi.fn() } };
});
vi.mock('../../lib/push/webPush', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/push/webPush')>();
  return { ...actual, enablePushNotifications: vi.fn() };
});

const mockedConfig = vi.mocked(api.getPushConfig);
const mockedEnable = vi.mocked(enablePushNotifications);
const ENABLED = { enabled: true, vapidPublicKey: 'BCle' };

function browser(overrides: Partial<PushBrowser> = {}): PushBrowser {
  return {
    supported: true,
    needsInstall: false,
    permission: () => 'default',
    requestPermission: vi.fn(),
    registration: vi.fn(),
    ...overrides,
  };
}

describe('PushNotificationsPrompt', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockedConfig.mockReset().mockResolvedValue(ENABLED);
    mockedEnable.mockReset();
  });

  afterEach(cleanup);

  it("propose d'activer, sans jamais demander la permission au chargement", async () => {
    const push = browser();
    render(<PushNotificationsPrompt browser={push} />);

    expect(await screen.findByRole('heading', { name: 'Ne manquez aucun message' })).toBeVisible();
    expect(push.requestPermission).not.toHaveBeenCalled();
    expect(mockedEnable).not.toHaveBeenCalled();
  });

  it('« Activer » abonne l’appareil avec la configuration déjà chargée', async () => {
    mockedEnable.mockResolvedValue('enabled');
    const push = browser();
    render(<PushNotificationsPrompt browser={push} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Activer' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Notifications activées');
    expect(mockedEnable).toHaveBeenCalledWith(api, push, ENABLED);
  });

  it('permission refusée : explique comment la rétablir', async () => {
    mockedEnable.mockResolvedValue('denied');
    render(<PushNotificationsPrompt browser={browser()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Activer' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Notifications bloquées');
  });

  it('échec technique : message clair, invitation conservée', async () => {
    mockedEnable.mockRejectedValue(new Error('panne'));
    render(<PushNotificationsPrompt browser={browser()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Activer' }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Impossible d'activer");
    expect(screen.getByRole('button', { name: 'Activer' })).toBeEnabled();
  });

  it('« Masquer » la retire durablement sur ce navigateur', async () => {
    const { unmount } = render(<PushNotificationsPrompt browser={browser()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Masquer cette invitation' }));

    expect(screen.queryByRole('heading', { name: 'Ne manquez aucun message' })).toBeNull();
    expect(window.localStorage.getItem(PUSH_PROMPT_DISMISSED_KEY)).toBe('1');
    unmount();
    render(<PushNotificationsPrompt browser={browser()} />);
    expect(mockedConfig).toHaveBeenCalledTimes(1); // plus aucun appel une fois masquée
  });

  it.each([
    ['notifications désactivées côté serveur', browser(), { enabled: false, vapidPublicKey: null }],
    ['permission déjà accordée', browser({ permission: () => 'granted' }), ENABLED],
    ['permission déjà refusée', browser({ permission: () => 'denied' }), ENABLED],
  ])('%s : rien n’est affiché', async (_label, push, config) => {
    mockedConfig.mockResolvedValue(config);
    const { container } = render(<PushNotificationsPrompt browser={push} />);

    await vi.waitFor(() => expect(mockedConfig).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('navigateur sans Web Push : rien, pas même un appel au serveur', () => {
    const { container } = render(
      <PushNotificationsPrompt browser={browser({ supported: false })} />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(mockedConfig).not.toHaveBeenCalled();
  });

  it("iPhone dans Safari : explique qu'il faut installer l'app", async () => {
    render(<PushNotificationsPrompt browser={browser({ supported: false, needsInstall: true })} />);

    expect(await screen.findByText(/installez d'abord l'app/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Activer' })).toBeNull();
  });
});
