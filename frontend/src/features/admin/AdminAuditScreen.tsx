import React, { useEffect, useState } from 'react';
import { ScrollText } from 'lucide-react';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { SelectField } from '../../components/ui/Field';
import { Skeleton } from '../../components/ui/Skeleton';
import { api } from '../../lib/api';
import { useAsyncResource } from '../../lib/useAsyncResource';
import type { AuditAction, AuditEntry, AuditTargetType, PageResult } from '../../types/admin';
import { AUDIT_ACTION_LABELS, AUDIT_TARGET_LABELS } from './adminText';
import { AuditEntryView } from './components/AuditEntryView';
import { Pager } from './components/Pager';

/**
 * Journal d'audit (/admin/journal), en LECTURE SEULE : chaque action admin
 * sensible y est inscrite dans la même transaction que l'action. La base
 * refuse toute modification ou suppression d'une ligne (ajout seul) ; aucune
 * interface ne propose donc de l'éditer.
 */
export const AdminAuditScreen: React.FC = () => {
  const [action, setAction] = useState<AuditAction | ''>('');
  const [targetType, setTargetType] = useState<AuditTargetType | ''>('');
  const [page, setPage] = useState(1);
  const { data, isLoading, error, run, reload } = useAsyncResource<PageResult<AuditEntry>>();

  useEffect(() => {
    run(() =>
      api.listAuditEntries({
        action: action || undefined,
        targetType: targetType || undefined,
        page,
      }),
    );
  }, [run, action, targetType, page]);

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="font-display text-display-md font-semibold text-primary">Journal</h1>
        <p className="text-sm text-muted-foreground">
          Toutes les actions admin sensibles, plus récentes d’abord. Le journal est en ajout seul :
          personne ne peut le modifier ni l’effacer.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <SelectField
          label="Action"
          value={action}
          onChange={(event) => {
            setAction(event.target.value as AuditAction | '');
            setPage(1);
          }}
        >
          <option value="">Toutes les actions</option>
          {(Object.keys(AUDIT_ACTION_LABELS) as AuditAction[]).map((key) => (
            <option key={key} value={key}>
              {AUDIT_ACTION_LABELS[key]}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Cible"
          value={targetType}
          onChange={(event) => {
            setTargetType(event.target.value as AuditTargetType | '');
            setPage(1);
          }}
        >
          <option value="">Toutes les cibles</option>
          {(Object.keys(AUDIT_TARGET_LABELS) as AuditTargetType[]).map((key) => (
            <option key={key} value={key}>
              {AUDIT_TARGET_LABELS[key]}
            </option>
          ))}
        </SelectField>
      </div>

      {isLoading && !data ? (
        <Skeleton className="h-64 rounded-card" />
      ) : error && !data ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : data && data.items.length === 0 ? (
        <EmptyState
          icon={<ScrollText />}
          title={action || targetType ? 'Aucune entrée ne correspond.' : 'Journal vide.'}
          description="Chaque décision admin y apparaîtra."
        />
      ) : data ? (
        <>
          <Card padding="none" className="overflow-hidden">
            <ol className="divide-y divide-border">
              {data.items.map((entry) => (
                <li key={entry.id} className="px-4 py-3">
                  <AuditEntryView entry={entry} />
                </li>
              ))}
            </ol>
          </Card>
          <Pager
            page={data.page}
            totalPages={data.totalPages}
            total={data.total}
            onPageChange={setPage}
          />
        </>
      ) : null}
    </div>
  );
};
