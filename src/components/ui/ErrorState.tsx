import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface ErrorStateProps {
  message: string;
  onRetry: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ message, onRetry, className = '' }) => (
  <div
    className={`flex flex-col items-center justify-center text-center gap-3 py-10 px-4 ${className}`}
  >
    <AlertTriangle className="w-9 h-9 text-destructive" />
    <p className="text-sm text-muted-foreground max-w-xs">{message}</p>
    <button
      onClick={onRetry}
      className="px-5 py-2.5 rounded-full bg-primary text-white font-sora text-xs font-bold hover:opacity-90 active:scale-95 transition-all cursor-pointer"
    >
      Réessayer
    </button>
  </div>
);
