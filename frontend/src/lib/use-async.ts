"use client";

import * as React from "react";

import { NetworkError } from "@/lib/api-error";

/**
 * Small data-fetch hook for list/detail screens:
 * - `loading` starts true and stays true across `deps` changes.
 * - `error` is a human-readable, already-mapped message (never a stack trace).
 * - `reload()` re-runs the loader without changing `deps`.
 * - Unmounted results are discarded.
 *
 * The loader is captured in a ref, so callers may pass an inline arrow
 * without causing re-fetch loops; re-fetches are driven by `deps` only.
 */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: ReadonlyArray<unknown>
): {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** Re-run the loader (e.g. after a retry action or a mutation). */
  reload: () => void;
} {
  const [nonce, setNonce] = React.useState(0);
  const loaderRef = React.useRef(loader);
  loaderRef.current = loader;

  const [data, setData] = React.useState<T | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    loaderRef
      .current()
      .then(
        (result) => {
          if (active) {
            setData(result);
            setLoading(false);
          }
        },
        (cause: unknown) => {
          if (!active) return;
          setData(null);
          setLoading(false);
          // ApiError and NetworkError both carry actionable messages.
          setError(
            cause instanceof NetworkError || cause instanceof Error
              ? cause.message
              : "Something went wrong. Try again."
          );
        }
      );
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = React.useCallback(() => setNonce((n) => n + 1), []);

  return { data, loading, error, reload };
}

/** Human-readable message for a caught error, safe for display (no stack). */
export function errorMessage(cause: unknown): string {
  if (cause instanceof NetworkError || cause instanceof Error) {
    return cause.message;
  }
  return "Something went wrong. Try again.";
}
