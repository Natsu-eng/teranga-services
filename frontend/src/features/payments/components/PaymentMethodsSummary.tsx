import React from 'react';
import { Banknote, CreditCard } from 'lucide-react';
import { Card } from '../../../components/ui/Card';
import { ErrorState } from '../../../components/ui/ErrorState';
import { Skeleton } from '../../../components/ui/Skeleton';
import { StatusPill } from '../../../components/ui/StatusPill';
import { cn } from '../../../lib/cn';
import type { PaymentChannel } from '../../../types';
import { usePaymentOptions } from '../hooks/usePaymentOptions';
import { CHANNEL_LABELS, paymentMethodsText } from '../paymentText';

/**
 * Pastille de chaque moyen : présentation seulement (couleur de marque,
 * sigle ou icône) -- la LISTE des moyens vient toujours du serveur.
 */
const CHANNEL_MARK: Record<PaymentChannel, { mark: React.ReactNode; className: string }> = {
  wave: { mark: 'W', className: 'bg-brand-wave text-foreground' },
  orange_money: { mark: 'OM', className: 'bg-brand-orange-money text-foreground' },
  free_money: { mark: 'FM', className: 'bg-surface-muted text-foreground' },
  carte: {
    mark: <CreditCard className="w-4 h-4" />,
    className: 'bg-emerald-tint text-primary-emerald',
  },
  cash: {
    mark: <Banknote className="w-4 h-4" />,
    className: 'bg-emerald-tint text-primary-emerald',
  },
};

const MethodChip: React.FC<{ channel: PaymentChannel; upcoming?: boolean }> = ({
  channel,
  upcoming = false,
}) => {
  const { mark, className } = CHANNEL_MARK[channel];
  return (
    <li
      className={cn(
        'inline-flex items-center gap-2 rounded-full bg-surface-muted pl-1 pr-3 py-1 text-sm',
        upcoming ? 'text-muted-foreground' : 'text-foreground',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'inline-flex w-7 h-7 items-center justify-center rounded-full text-xs font-bold',
          className,
          // Moyen pas encore disponible : grisé, jamais présenté comme utilisable.
          upcoming && 'opacity-40 grayscale',
        )}
      >
        {mark}
      </span>
      {CHANNEL_LABELS[channel]}
      {upcoming && <StatusPill tone="neutral">Bientôt</StatusPill>}
    </li>
  );
};

/**
 * Moyens de paiement du client (profil), tels que l'instance les propose
 * VRAIMENT : espèces quand elles sont acceptées, moyens en ligne actifs, et
 * moyens prévus marqués « Bientôt ». La protection par séquestre n'est
 * évoquée que si le paiement en ligne est réellement actif.
 */
export const PaymentMethodsSummary: React.FC = () => {
  const { data: options, isLoading, error, reload } = usePaymentOptions();

  if (isLoading && !options) return <Skeleton className="h-28 rounded-card" />;
  if (error && !options) return <ErrorState message={error.message} onRetry={reload} />;
  if (!options) return null;

  return (
    <Card className="space-y-3">
      <ul aria-label="Moyens de paiement" className="flex flex-wrap gap-2">
        {options.cashEnabled && <MethodChip channel="cash" />}
        {options.onlineChannels.map((channel) => (
          <MethodChip key={channel} channel={channel} />
        ))}
        {options.upcomingChannels.map((channel) => (
          <MethodChip key={channel} channel={channel} upcoming />
        ))}
      </ul>
      <p className="text-sm text-muted-foreground">{paymentMethodsText(options)}</p>
    </Card>
  );
};
