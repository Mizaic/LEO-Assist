/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BCA9B190")
 */
"use client";

import type { ReactNode } from "react";
import { AnimatePresence, motion as fm } from "framer-motion";

import { useMotion } from "../motion";
import { springOrInstant, springs } from "../motion/springs";

export interface SpringSwapProps {
  swapKey: string;
  children: ReactNode;
}

/**
 * Interruptible enter/exit on the same vertical path.
 * Reduced motion drops the slide and keeps a short opacity cross-fade.
 */
export function SpringSwap({ swapKey, children }: SpringSwapProps) {
  const { reducedMotion } = useMotion();
  const fadeOnly = { opacity: 0 };
  const slide = { opacity: 0, y: 8 };

  return (
    <AnimatePresence mode="wait">
      <fm.div
        key={swapKey}
        data-testid="spring-swap"
        initial={reducedMotion ? fadeOnly : slide}
        animate={{ opacity: 1, y: 0 }}
        exit={reducedMotion ? fadeOnly : { opacity: 0, y: -8 }}
        transition={springOrInstant(reducedMotion, springs.ui)}
      >
        {children}
      </fm.div>
    </AnimatePresence>
  );
}
