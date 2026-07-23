import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from './api';

interface AsyncResourceState<T> {
  data: T | null;
  isLoading: boolean;
  error: ApiError | null;
}

function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError('unknown', 'Une erreur inattendue est survenue. Merci de réessayer.');
}

interface UseAsyncResourceOptions {
  /** Whether the resource starts in a loading state before the first `run()` call. */
  initialLoading?: boolean;
}

/**
 * Shared building block behind every feature data hook: runs an async call,
 * ignores it if a newer call has since started or the component has
 * unmounted (guards against out-of-order responses and setState-after-unmount),
 * and exposes {data, isLoading, error} plus `run`/`reload`/`setData`.
 */
export function useAsyncResource<T>(options: UseAsyncResourceOptions = {}) {
  const { initialLoading = true } = options;
  const [state, setState] = useState<AsyncResourceState<T>>({
    data: null,
    isLoading: initialLoading,
    error: null,
  });

  const mountedRef = useRef(true);
  const callIdRef = useRef(0);
  const lastFactoryRef = useRef<(() => Promise<T>) | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const run = useCallback((factory: () => Promise<T>) => {
    lastFactoryRef.current = factory;
    const callId = ++callIdRef.current;
    setState((prev) => ({ data: prev.data, isLoading: true, error: null }));

    factory()
      .then((data) => {
        if (!mountedRef.current || callIdRef.current !== callId) return;
        setState({ data, isLoading: false, error: null });
      })
      .catch((err) => {
        if (!mountedRef.current || callIdRef.current !== callId) return;
        setState((prev) => ({ data: prev.data, isLoading: false, error: toApiError(err) }));
      });
  }, []);

  const reload = useCallback(() => {
    if (lastFactoryRef.current) run(lastFactoryRef.current);
  }, [run]);

  const setData = useCallback((updater: (prev: T | null) => T | null) => {
    setState((prev) => ({ ...prev, data: updater(prev.data) }));
  }, []);

  return { data: state.data, isLoading: state.isLoading, error: state.error, run, reload, setData };
}
