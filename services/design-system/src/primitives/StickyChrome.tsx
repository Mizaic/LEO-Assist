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

import { useReducedTransparency } from "../motion/useReducedTransparency";
import { color } from "../tokens/color";
import { frostStyle } from "../tokens/material";
import { elevation } from "../tokens/spacing";

export interface StickyChromeProps {
  children: ReactNode;
  testId?: string;
}

/**
 * Translucent sticky control layer. Content scrolls underneath.
 * A bright top edge reads as light catching the material, not a hard divider.
 */
export function StickyChrome({ children, testId = "sticky-chrome" }: StickyChromeProps) {
  const reducedTransparency = useReducedTransparency();
  const frost = frostStyle(reducedTransparency, "light");

  return (
    <div
      data-testid={testId}
      style={{
        position: "sticky",
        top: 0,
        zIndex: 8,
        margin: "0 -8px 12px",
        padding: "8px 8px 12px",
        ...frost,
        borderTop: "1px solid rgba(255, 255, 255, 0.7)",
        boxShadow: elevation.card,
        borderBottom: reducedTransparency
          ? "1px solid " + color.surface.divider
          : "1px solid rgba(226, 232, 240, 0.55)",
      }}
    >
      {children}
    </div>
  );
}
