import { useCallback } from 'react';
import type { AIAnalysisResult } from '../../../types';
import { api } from '../../../lib/api';
import { useAsyncResource } from '../../../lib/useAsyncResource';

// Manual trigger, not auto-fetched on mount: the caller decides when the
// description is ready to analyze.
export function useAnalyzeProblem() {
  const { data, isLoading, error, run } = useAsyncResource<AIAnalysisResult>({
    initialLoading: false,
  });

  const analyze = useCallback(
    (description: string) => {
      run(() => api.analyzeProblem(description));
    },
    [run],
  );

  return { data, isLoading, error, analyze };
}
