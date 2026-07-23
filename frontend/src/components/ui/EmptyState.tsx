import React from 'react';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className = '',
}) => (
  <div className={`bg-white rounded-2xl p-8 text-center border border-border ${className}`}>
    {icon}
    <p className="text-muted-foreground font-medium mt-2">{title}</p>
    {description && <p className="text-xs text-muted-foreground-soft mt-1">{description}</p>}
    {action && (
      <button
        onClick={action.onClick}
        className="mt-3 text-sm font-sora text-primary underline cursor-pointer"
      >
        {action.label}
      </button>
    )}
  </div>
);
