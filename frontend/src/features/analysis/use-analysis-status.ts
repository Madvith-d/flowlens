"use client";

import * as React from "react";

import { ApiError } from "@/lib/api-error";
import { errorMessage } from "@/lib/use-async";
import type { AnalysisRun } from "@/types/api";
import {
  getAnalysis,
  isPendingState,
} from "@/features/analysis/analysis-service";

/**
 * Bounded analysis status polling.
 *
 * - Polls `GET /api/v1/analyses/{id}` while the run is `queued`/`running`.
 * - Stops on terminal states, unmount, poll errors, or after `MAX_POLLS`
 *   attempts (the UI then offers an honest manual refresh instead of
 *   pretending the run is still being watched).
 * - No progress is fabricated: only the backend state is shown.
 */

const POLL_INTERVAL_MS = 2_000;
/** ~10 minutes at 2s per poll; afterwards the user refreshes manually. */
const MAX_POLLS = 300;

export interface AnalysisStatus {
  /** Current run data (initial value until/unless a poll updates it). */
  analysis: AnalysisRun | null;
  /** True while queued/running and polling has not given up. */
  polling: boolean;
  /** Poll iteration failed — displayed with a retry (manual refresh). */
  pollError: string | null;
  /** Polling stopped because MAX_POLLS was reached; manual refresh needed. */
  pollLimitReached: boolean;
  /** Manual refresh of the run by id (retry after an error or limit). */
  refresh: () => void;
}

export function useAnalysisStatus(initial: AnalysisRun | null): AnalysisStatus {
  const [current, setCurrent] = React.useState<AnalysisRun | null>(initial);
  const [pollError, setPollError] = React.useState<string | null>(null);
  const [pollLimitReached, setPollLimitReached] = React.useState(false);
  const [refreshNonce, setRefreshNonce] = React.useState(0);

  // Adopt a new run when the caller switches to a different analysis id.
  const initialId = initial?.id ?? null;
  const currentId = current?.id ?? null;
  React.useEffect(() => {
    if (initialId !== currentId) {
      setCurrent(initial);
      setPollError(null);
      setPollLimitReached(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialId, currentId]);

  // Manual refresh path (also the initial fetch for `initial === null`
  // is not attempted: with no run, there is nothing to poll or refresh).
  React.useEffect(() => {
    if (refreshNonce === 0 || !currentId) return;
    let active = true;
    getAnalysis(currentId)
      .then(
        (run) => {
          if (active) {
            setCurrent(run);
            setPollError(null);
            setPollLimitReached(false);
          }
        },
        (cause) => {
          if (active) setPollError(errorMessage(cause));
        }
      );
    return () => {
      active = false;
    };
  }, [refreshNonce, currentId]);

  const pending = current !== null && isPendingState(current.state);
  const polling = pending && !pollError && !pollLimitReached;

  // Bounded polling loop while the run is queued/running.
  React.useEffect(() => {
    if (!current|| !polling) return;
    let cancelled = false;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const scheduleNext = (delayMs: number) => {
      timer = setTimeout(async () => {
        if (cancelled) return;
        attempts += 1;
        if (attempts > MAX_POLLS) {
          // Honest stop: the backend has not reached a terminal state
          // within the polling budget. The user can refresh manually.
          setPollLimitReached(true);
          return;
        }
        try {
          const run = await getAnalysis(current.id);
          if (cancelled) return;
          setCurrent(run);
          setPollError(null);
          if (isPendingState(run.state)) scheduleNext(POLL_INTERVAL_MS);
        } catch (cause) {
          if (cancelled) return;
          setPollError(
            cause instanceof ApiError || cause instanceof Error
              ? cause.message
              : "Could not refresh the analysis status."
          );
        }
      }, delayMs);
    };

    scheduleNext(POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId, polling]);

  const refresh = React.useCallback(() => setRefreshNonce((n) => n + 1), []);

  return {
    analysis: current,
    polling,
    pollError,
    pollLimitReached,
    refresh,
  };
}
