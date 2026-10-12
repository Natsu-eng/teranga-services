import React, { useEffect, useState } from 'react';
import { ShieldCheck, ShieldOff, Users } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Chip } from '../../components/ui/Chip';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusPill } from '../../components/ui/StatusPill';
import { api } from '../../lib/api';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { AccountRole, AdminUser, PageResult } from '../../types/admin';
import { ROLE_LABELS, formatAdminDate } from './adminText';
import { ConfirmActionSheet } from './components/ConfirmActionSheet';
import { Pager } from './components/Pager';
import { SearchBar } from './components/SearchBar';

const FILTERS: { value: AccountRole | null; label: string }[] = [
  { value: null, label: 'Tous' },
  { value: 'admin', label: 'Admins' },
  { value: 'client', label: 'Clients' },
  { value: 'artisan', label: 'Artisans' },
];

const UserRow: React.FC<{ user: AdminUser; onAction: (action: 'grant' | 'revoke') => void }> = ({
  user,
  onAction,
}) => (
  <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
    <div className="min-w-0 space-y-1">
      <p className="font-medium text-foreground">
        {user.fullName}
        {user.isSelf && <span className="text-muted-foreground"> (vous)</span>}
      </p>
      <p className="text-sm text-muted-foreground">
        {user.phone} · inscrit le {formatAdminDate(user.createdAt)}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone={user.role === 'admin' ? 'info' : 'neutral'}>
          {ROLE_LABELS[user.role]}
        </StatusPill>
        {user.role === 'admin' && user.hasArtisanProfile && (
          <span className="text-xs text-muted-foreground">profil artisan existant</span>
        )}
      </div>
      {/* Garde-fou dit AVANT toute tentative : pourquoi l'action n'est pas possible. */}
      {user.guard && <p className="text-xs text-muted-foreground">{user.guard}</p>}
    </div>
    {user.canGrantAdmin && (
      <Button
        variant="outline"
        size="sm"
        leadingIcon={<ShieldCheck aria-hidden className="w-4 h-4" />}
        onClick={() => onAction('grant')}
      >
        Accorder le rôle admin
      </Button>
    )}
    {user.canRevokeAdmin && (
      <Button
        variant="danger-outline"
        size="sm"
        leadingIcon={<ShieldOff aria-hidden className="w-4 h-4" />}
        onClick={() => onAction('revoke')}
      >
        Retirer le rôle admin
      </Button>
    )}
  </li>
);

/**
 * Utilisateurs (/admin/utilisateurs) : octroi et retrait du rôle admin.
 * Les garde-fous (jamais son propre rôle, jamais le dernier admin, comptes
 * admin dédiés) sont affichés sur chaque ligne ET revérifiés par le serveur
 * sous verrou : l'affichage n'autorise rien, il informe.
 */
export const AdminUsersScreen: React.FC = () => {
  const [role, setRole] = useState<AccountRole | null>(null);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<{ user: AdminUser; action: 'grant' | 'revoke' } | null>(
    null,
  );
  const { data, isLoading, error, run, reload } = useAsyncResource<PageResult<AdminUser>>();

  useEffect(() => {
    run(() => api.listAdminUsers({ role: role ?? undefined, q, page }));
  }, [run, role, q, page]);

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="font-display text-display-md font-semibold text-primary">Utilisateurs</h1>
        <p className="text-sm text-muted-foreground">Gestion du rôle administrateur.</p>
      </div>

      <Card as="aside" padding="md" tone="default" className="text-sm text-foreground space-y-1">
        <p className="font-semibold">Règles de sécurité</p>
        <ul className="list-disc pl-5 space-y-0.5 text-muted-foreground">
          <li>Vous ne pouvez jamais retirer votre propre rôle.</li>
          <li>Le dernier administrateur ne peut pas être retiré.</li>
          <li>
            Seul un compte client dédié peut devenir admin (jamais un compte artisan, qui perdrait
            son espace Pro).
          </li>
          <li>Tout changement prend effet immédiatement et est inscrit au journal.</li>
        </ul>
      </Card>

      <SearchBar
        label="Rechercher un compte"
        placeholder="Nom ou téléphone"
        onSearch={(value) => {
          setQ(value);
          setPage(1);
        }}
      />
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrer par rôle">
        {FILTERS.map((filter) => (
          <Chip
            key={filter.label}
            selected={role === filter.value}
            onClick={() => {
              setRole(filter.value);
              setPage(1);
            }}
          >
            {filter.label}
          </Chip>
        ))}
      </div>

      {isLoading && !data ? (
        <Skeleton className="h-64 rounded-card" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : data && data.items.length === 0 ? (
        <EmptyState icon={<Users />} title="Aucun compte ne correspond." />
      ) : data ? (
        <>
          <Card padding="none" className="overflow-hidden">
            <ul className="divide-y divide-border">
              {data.items.map((user) => (
                <UserRow
                  key={user.id}
                  user={user}
                  onAction={(action) => setPending({ user, action })}
                />
              ))}
            </ul>
          </Card>
          <Pager
            page={data.page}
            totalPages={data.totalPages}
            total={data.total}
            onPageChange={setPage}
          />
        </>
      ) : null}

      <ConfirmActionSheet
        open={pending?.action === 'grant'}
        onClose={() => setPending(null)}
        title={`Accorder le rôle admin à ${pending?.user.fullName ?? ''}`}
        confirmLabel="Accorder le rôle admin"
        effect="Ce compte accède immédiatement à tout le back-office : documents d’identité, litiges, argent, rôles et commissions."
        reason={{ label: 'Note', mode: 'optional' }}
        onConfirm={async (note) => {
          if (!pending) return;
          await api.grantAdmin(pending.user.id, note);
          // Rechargée : les garde-fous des autres lignes (dernier admin) changent aussi.
          reload();
        }}
      />
      <ConfirmActionSheet
        open={pending?.action === 'revoke'}
        onClose={() => setPending(null)}
        title={`Retirer le rôle admin de ${pending?.user.fullName ?? ''}`}
        tone="danger"
        confirmLabel="Retirer le rôle admin"
        effect={`Son accès au back-office est coupé dès sa prochaine action. Son compte redevient ${
          pending?.user.hasArtisanProfile ? 'artisan' : 'client'
        }.`}
        reason={{ label: 'Note', mode: 'optional' }}
        onConfirm={async (note) => {
          if (!pending) return;
          await api.revokeAdmin(pending.user.id, note);
          reload();
        }}
      />
    </div>
  );
};
