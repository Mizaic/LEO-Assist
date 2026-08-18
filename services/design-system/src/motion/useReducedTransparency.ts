/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-6DCC699A
 *   DI: DI-9DDC5471
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-6DCC699A")
 */
"use client";

import { useEffect, useState } from "react";

function readPreference(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  try {
    return window.matchMedia("(prefers-reduced-transparency: reduce)").matches;
  } catch {
    return false;
  }
}

/**
 * Frosted materials fall back to solid when the user asks for less
 * transparency. Independent of prefers-reduced-motion.
 */
export function useReducedTransparency(): boolean {
  const [reduce, setReduce] = useState(false);

  useEffect(() => {
    setReduce(readPreference());
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-transparency: reduce)");
    const onChange = (event: MediaQueryListEvent) => setReduce(event.matches);
    if (mql.addEventListener) {
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    }
    mql.addListener(onChange);
    return () => mql.removeListener(onChange);
  }, []);

  return reduce;
}
