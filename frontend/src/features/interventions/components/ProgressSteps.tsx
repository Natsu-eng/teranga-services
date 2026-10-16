import React from 'react';
import { cn } from '../../../lib/cn';
import { STEPS } from '../interventionText';

/** Frise d'avancement : l'étape courante est annoncée aux lecteurs d'écran. */
export const ProgressSteps: React.FC<{ current: number }> = ({ current }) => (
  <ol aria-label="Avancement" className="grid grid-cols-4 gap-1.5">
    {STEPS.map((step, index) => {
      const isDone = index < current || (index === current && index === STEPS.length - 1);
      const isCurrent = index === current;
      return (
        <li key={step} className="space-y-1.5" aria-current={isCurrent ? 'step' : undefined}>
          <span
            aria-hidden
            className={cn(
              'block h-1.5 rounded-full',
              isDone || isCurrent ? 'bg-primary-emerald' : 'bg-border-subtle',
            )}
          />
          <span
            className={cn(
              'block text-caption leading-tight',
              isCurrent ? 'font-semibold text-primary' : 'text-muted-foreground',
            )}
          >
            {step}
          </span>
        </li>
      );
    })}
  </ol>
);
