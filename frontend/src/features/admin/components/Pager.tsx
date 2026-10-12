import React from 'react';
import { Button } from '../../../components/ui/Button';

interface PagerProps {
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
}

/** Pagination simple (précédent / suivant) d'une liste paginée par le serveur. */
export const Pager: React.FC<PagerProps> = ({ page, totalPages, total, onPageChange }) => {
  if (totalPages <= 1) {
    return (
      <p className="text-sm text-muted-foreground">
        {total} résultat{total > 1 ? 's' : ''}
      </p>
    );
  }
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3">
      <Button
        variant="outline"
        size="sm"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        Précédent
      </Button>
      <p className="text-sm text-muted-foreground">
        Page {page} sur {totalPages} · {total} résultats
      </p>
      <Button
        variant="outline"
        size="sm"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        Suivant
      </Button>
    </nav>
  );
};
