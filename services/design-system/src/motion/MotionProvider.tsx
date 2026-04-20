/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-6DCC699A
 *   DI: DI-9DDC5471
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-6DCC699A")
 */
"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { motion, reducedMotion } from "../tokens/motion";

export interface MotionContextValue {
  reducedMotion: boolean;
  transitions: typeof motion;
}

const defaultValue: MotionContextValue = {
  reducedMotion: false,
  transitions: motion,
};

export const MotionContext =
  createContext<MotionContextValue>(defaultValue);

function readPreference(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export function MotionProvider({ children }: { children: ReactNode }) {
  const [reduce, setReduce] = useState<boolean>(false);

  useEffect(() => {
    setReduce(readPreference());
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (e: MediaQueryListEvent) => setReduce(e.matches);
    if (mql.addEventListener) {
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    }
    mql.addListener(onChange);
    return () => mql.removeListener(onChange);
  }, []);

  const value = useMemo<MotionContextValue>(
    () => ({
      reducedMotion: reduce,
      transitions: reduce
        ? (reducedMotion(motion) as unknown as typeof motion)
        : motion,
    }),
    [reduce],
  );

  return (
    <MotionContext.Provider value={value}>{children}</MotionContext.Provider>
  );
}

export function useMotion(): MotionContextValue {
  return useContext(MotionContext);
}
