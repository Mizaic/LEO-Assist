/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BCA9B190")
 */
"use client";

import { useCallback, useLayoutEffect, useState, type RefObject } from "react";

export interface PillRect {
  x: number;
  width: number;
  ready: boolean;
}

const HIDDEN: PillRect = { x: 0, width: 0, ready: false };

/**
 * Measures the active segmented-tab button so a spring pill can track
 * it from the live on-screen position (interruptible, no jump).
 */
export function useSegmentedPill(
  listRef: RefObject<HTMLElement | null>,
  buttonRefs: RefObject<Array<HTMLElement | null>>,
  activeIdx: number,
): PillRect {
  const [pill, setPill] = useState<PillRect>(HIDDEN);

  const measure = useCallback(() => {
    const btn = buttonRefs.current?.[activeIdx];
    if (!btn) return;
    setPill({ x: btn.offsetLeft, width: btn.offsetWidth, ready: true });
  }, [activeIdx, buttonRefs]);

  useLayoutEffect(() => {
    measure();
    const list = listRef.current;
    if (!list || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    return () => observer.disconnect();
  }, [listRef, measure]);

  return pill;
}
