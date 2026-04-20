/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5D525D34
 *   DI: DI-522BBCC4
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5D525D34")
 */
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
import { useAuth } from "@/lib/authContext";

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

function isDensityTier(value: unknown): value is DensityTier {
  return value === "compact" || value === "comfortable" || value === "spacious";
}

export function resolveInitialDensity(
  pathname: string | null | undefined,
  stored: DensityTier | null,
  serverPreference?: DensityTier | null,
): DensityTier {
  if (isPatientReachableRoute(pathname)) return DEFAULT_PATIENT;
  if (serverPreference) return serverPreference;
  if (stored) return stored;
  return DEFAULT_STAFF;
}

interface DensityContextValue {
  density: DensityTier;
  setDensity: (next: DensityTier) => void;
  tokens: (typeof DENSITY_MAP)[DensityTier];
  isRouteForced: boolean;
  isPersisting: boolean;
}

const DensityContext = createContext<DensityContextValue | null>(null);

export function DensityProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const auth = useAuth();
  const serverPreference = auth.session?.densityPreference ?? null;
  const [stored, setStored] = useState<DensityTier | null>(null);
  const [isPersisting, setIsPersisting] = useState(false);

  useEffect(() => {
    setStored(readStoredDensity());
  }, []);

  const isRouteForced = isPatientReachableRoute(pathname);
  const density: DensityTier = useMemo(
    () => resolveInitialDensity(pathname, stored, serverPreference),
    [pathname, stored, serverPreference],
  );

  const persistToServer = useCallback(
    async (next: DensityTier) => {
      if (!auth.session?.user?.email) return;
      setIsPersisting(true);
      try {
        await fetch("/auth/session/density", {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ density: next }),
        });
        await auth.refetch();
      } catch {
        /* fail-soft: localStorage already updated */
      } finally {
        setIsPersisting(false);
      }
    },
    [auth],
  );

  const setDensity = useCallback(
    (next: DensityTier) => {
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* ignore storage failures (private mode, quota) */
      }
      setStored(next);
      void persistToServer(next);
    },
    [persistToServer],
  );

  const value: DensityContextValue = useMemo(
    () => ({
      density,
      setDensity,
      tokens: DENSITY_MAP[density],
      isRouteForced,
      isPersisting,
    }),
    [density, setDensity, isRouteForced, isPersisting],
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
      isPersisting: false,
    };
  }
  return ctx;
}

export function useDensityTokens() {
  return useDensity().tokens;
}

export const DENSITY_TIERS: DensityTier[] = [
  "compact",
  "comfortable",
  "spacious",
];

export function isDensityValue(value: unknown): value is DensityTier {
  return isDensityTier(value);
}
