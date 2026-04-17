"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import {
  DENSITY_MAP,
  DensityTier,
  isPatientReachableRoute,
} from "@/theme/tokens";

const STORAGE_KEY = "leo-density";
const DEFAULT_STAFF: DensityTier = "comfortable";
const DEFAULT_PATIENT: DensityTier = "spacious";

function readStoredDensity(): DensityTier | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "compact" || raw === "comfortable" || raw === "spacious") {
      return raw;
    }
    return null;
  } catch {
    return null;
  }
}

export function resolveInitialDensity(
  pathname: string | null | undefined,
  stored: DensityTier | null,
): DensityTier {
  if (isPatientReachableRoute(pathname)) return DEFAULT_PATIENT;
  if (stored) return stored;
  return DEFAULT_STAFF;
}

interface DensityContextValue {
  density: DensityTier;
  setDensity: (next: DensityTier) => void;
  tokens: (typeof DENSITY_MAP)[DensityTier];
  isRouteForced: boolean;
}

const DensityContext = createContext<DensityContextValue | null>(null);

export function DensityProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [stored, setStored] = useState<DensityTier | null>(null);

  useEffect(() => {
    setStored(readStoredDensity());
  }, []);

  const isRouteForced = isPatientReachableRoute(pathname);
  const density: DensityTier = useMemo(
    () => resolveInitialDensity(pathname, stored),
    [pathname, stored],
  );

  const setDensity = useCallback((next: DensityTier) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore storage failures (private mode, quota) */
    }
    setStored(next);
  }, []);

  const value: DensityContextValue = useMemo(
    () => ({
      density,
      setDensity,
      tokens: DENSITY_MAP[density],
      isRouteForced,
    }),
    [density, setDensity, isRouteForced],
  );

  return <DensityContext.Provider value={value}>{children}</DensityContext.Provider>;
}

export function useDensity(): DensityContextValue {
  const ctx = useContext(DensityContext);
  if (!ctx) {
    return {
      density: DEFAULT_STAFF,
      setDensity: () => {
        /* no-op outside provider */
      },
      tokens: DENSITY_MAP[DEFAULT_STAFF],
      isRouteForced: false,
    };
  }
  return ctx;
}

export function useDensityTokens() {
  return useDensity().tokens;
}
