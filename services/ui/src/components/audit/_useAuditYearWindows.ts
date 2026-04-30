/**
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 *
 * Shared hook for the /care/audit "year-on-year evolution" section
 * pattern: render four cards (2018 baseline + currentYear-2 / -1 /
 * current) and have each card show the same metric scoped to its
 * Jan-Dec calendar window.
 *
 * Every section endpoint shares the same backend filter -- the
 * `outcome_date` anchor (year of diagnosis or benign closure) bound by
 * `_OUTCOME_DATE_BIND` in services/analytics_api/app/routers/_audit_helpers.py
 * -- so each card on the report consumes the same denominator
 * for the same year.
 *
 * The 2018 baseline values are NOT fetched here; they come from the
 * `result.benchmark` envelope on the page-level prop and are rendered
 * by each section using its own benchmark accessor.
 */

import { useEffect, useMemo, useState } from "react";

import type { AuditSectionResult } from "@/lib/analyticsApi";

export interface AuditYearState<T> {
  year: number;
  loading: boolean;
  data: T | null;
  error: string | null;
}

export interface UseAuditYearWindowsResult<T> {
  /** Live year states ordered chronologically (Y-2, Y-1, Y). */
  liveYears: AuditYearState<T>[];
  /** True until every year fetch resolves (success or failure). */
  anyLoading: boolean;
  /** True when no live year produced any rows -- sections render an empty state. */
  allYearsEmpty: boolean;
}

export type SectionFetcher<T> = (
  orgId: string | undefined,
  dateFrom: string,
  dateTo: string,
) => Promise<AuditSectionResult<T>>;

interface UseAuditYearWindowsOptions {
  orgId: string | null | undefined;
  /** Custom predicate to decide whether a year's data counts as non-empty. */
  isEmpty?: (data: unknown) => boolean;
}

function defaultIsEmpty(data: unknown): boolean {
  if (data == null) return true;
  if (Array.isArray(data)) return data.length === 0;
  if (typeof data === "object") return Object.keys(data as object).length === 0;
  return false;
}

function calendarYearWindow(year: number): { from: string; to: string } {
  return {
    from: `${year}-01-01`,
    to: `${year}-12-31`,
  };
}

/**
 * Fetch the same audit section endpoint for the previous two complete
 * calendar years and the current calendar year-to-date (UTC).
 *
 * The 2018 baseline card sits alongside these live years on every
 * evolution section but is rendered separately (from the page-level
 * `result.benchmark` prop) -- this hook only owns the *live* fetches.
 */
export function useAuditYearWindows<T>(
  fetcher: SectionFetcher<T>,
  options: UseAuditYearWindowsOptions,
): UseAuditYearWindowsResult<T> {
  const { orgId, isEmpty = defaultIsEmpty } = options;

  const currentYear = new Date().getUTCFullYear();
  const liveYearNumbers = useMemo(
    () => [currentYear - 2, currentYear - 1, currentYear],
    [currentYear],
  );

  const [yearStates, setYearStates] = useState<AuditYearState<T>[]>(() =>
    liveYearNumbers.map((year) => ({
      year,
      loading: true,
      data: null,
      error: null,
    })),
  );

  useEffect(() => {
    let cancelled = false;

    setYearStates(
      liveYearNumbers.map((year) => ({
        year,
        loading: true,
        data: null,
        error: null,
      })),
    );

    const orgArg = orgId ?? undefined;

    Promise.all(
      liveYearNumbers.map(async (year): Promise<AuditYearState<T>> => {
        const window = calendarYearWindow(year);
        try {
          const res = await fetcher(orgArg, window.from, window.to);
          return {
            year,
            loading: false,
            data: res?.scopes?.practice ?? null,
            error: null,
          };
        } catch (e) {
          return {
            year,
            loading: false,
            data: null,
            error:
              e instanceof Error
                ? e.message
                : `Unable to load ${year} data.`,
          };
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      setYearStates(results);
    });

    return () => {
      cancelled = true;
    };
    // fetcher is intentionally omitted -- callers pass `fetchAuditX` from
    // a stable module reference, so refetching on identity changes would
    // cause an infinite loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, liveYearNumbers]);

  const anyLoading = yearStates.some((s) => s.loading);
  const allYearsEmpty = yearStates.every(
    (s) => !s.loading && (s.data == null || isEmpty(s.data)),
  );

  return {
    liveYears: yearStates,
    anyLoading,
    allYearsEmpty,
  };
}

export const BASELINE_YEAR = 2018;
