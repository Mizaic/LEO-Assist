/**
 * Atlas trace:
 *   DO: DO-ACCEEF0C
 *   DI: DI-6FD9D8D1
 *   VT: VT-FA40F4D3
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

const STORAGE_KEY = "leo_demo_mode";

interface DemoModeContextValue {
  isDemoMode: boolean;
  setDemoMode: (enabled: boolean) => void;
}

const DemoModeContext = createContext<DemoModeContextValue | null>(null);

function readStoredDemoMode(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function DemoModeProvider({ children }: { children: ReactNode }) {
  const [isDemoMode, setIsDemoMode] = useState(false);

  useEffect(() => {
    setIsDemoMode(readStoredDemoMode());
  }, []);

  const setDemoMode = useCallback((enabled: boolean) => {
    setIsDemoMode(enabled);
    try {
      if (enabled) {
        window.localStorage.setItem(STORAGE_KEY, "true");
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      /* ignore storage failures (private mode, quota) */
    }
  }, []);

  const value = useMemo(
    () => ({ isDemoMode, setDemoMode }),
    [isDemoMode, setDemoMode],
  );

  return (
    <DemoModeContext.Provider value={value}>
      {children}
    </DemoModeContext.Provider>
  );
}

export function useDemoMode(): DemoModeContextValue {
  const ctx = useContext(DemoModeContext);
  if (!ctx) {
    return {
      isDemoMode: false,
      setDemoMode: () => {
        /* no-op outside provider */
      },
    };
  }
  return ctx;
}

export const DEMO_MODE_STORAGE_KEY = STORAGE_KEY;
