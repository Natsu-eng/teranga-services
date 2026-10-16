import React from 'react';
import { Check } from 'lucide-react';
import { cn } from '../../../lib/cn';

/** Une étape de la checklist, posée sur le bandeau vert profond. */
export const ChecklistItem: React.FC<{ done: boolean; label: string }> = ({ done, label }) => (
  <li className="flex items-center gap-3">
    <span
      aria-hidden
      className={cn(
        'inline-flex w-6 h-6 shrink-0 items-center justify-center rounded-full',
        done ? 'bg-accent text-primary' : 'ring-2 ring-inset ring-white/35',
      )}
    >
      {done && <Check className="w-4 h-4" strokeWidth={3} />}
    </span>
    <span
      className={cn(
        'text-sm',
        done ? 'text-white font-semibold' : 'text-primary-emerald-foreground',
      )}
    >
      {label}
      <span className="sr-only">{done ? ' : fait' : ' : à faire'}</span>
    </span>
  </li>
);
