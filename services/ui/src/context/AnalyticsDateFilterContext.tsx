/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "leo_analytics_date_range";

type StoredRange = { from?: string; to?: string };

function readStored(): StoredRange {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as StoredRange;
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

interface AnalyticsDateFilterValue {
  /** Draft values in the date inputs (yyyy-mm-dd). */
  dateFrom: string;
  dateTo: string;
  /** Applied filter passed to APIs. */
  appliedFrom: string | undefined;
  appliedTo: string | undefined;
  setDateFrom: (v: string) => void;
  setDateTo: (v: string) => void;
  /** Apply draft inputs as the active filter and persist. */
  apply: () => void;
  /** Set from/to and apply in one step (tax year presets). */
  applyPreset: (from: string, to: string) => void;
  clear: () => void;
  isFiltered: boolean;
}

const AnalyticsDateFilterContext = createContext<AnalyticsDateFilterValue | null>(null);

export function AnalyticsDateFilterProvider({ children }: { children: ReactNode }) {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [appliedFrom, setAppliedFrom] = useState<string | undefined>(undefined);
  const [appliedTo, setAppliedTo] = useState<string | undefined>(undefined);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const { from, to } = readStored();
    if (from || to) {
      setDateFrom(from ?? "");
      setDateTo(to ?? "");
      setAppliedFrom(from);
      setAppliedTo(to);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (appliedFrom || appliedTo) {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ from: appliedFrom, to: appliedTo }),
      );
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [hydrated, appliedFrom, appliedTo]);

  const apply = useCallback(() => {
    setAppliedFrom(dateFrom || undefined);
    setAppliedTo(dateTo || undefined);
  }, [dateFrom, dateTo]);

  const applyPreset = useCallback((from: string, to: string) => {
    setDateFrom(from);
    setDateTo(to);
    setAppliedFrom(from);
    setAppliedTo(to);
  }, []);

  const clear = useCallback(() => {
    setDateFrom("");
    setDateTo("");
    setAppliedFrom(undefined);
    setAppliedTo(undefined);
  }, []);

  const value = useMemo(
    (): AnalyticsDateFilterValue => ({
      dateFrom,
      dateTo,
      appliedFrom,
      appliedTo,
      setDateFrom,
      setDateTo,
      apply,
      applyPreset,
      clear,
      isFiltered: !!appliedFrom || !!appliedTo,
    }),
    [dateFrom, dateTo, appliedFrom, appliedTo, apply, applyPreset, clear],
  );

  return (
    <AnalyticsDateFilterContext.Provider value={value}>
      {children}
    </AnalyticsDateFilterContext.Provider>
  );
}

export function useAnalyticsDateFilter(): AnalyticsDateFilterValue {
  const ctx = useContext(AnalyticsDateFilterContext);
  if (!ctx) {
    throw new Error("useAnalyticsDateFilter must be used within AnalyticsDateFilterProvider");
  }
  return ctx;
}
