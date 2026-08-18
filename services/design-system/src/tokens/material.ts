/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
import type { CSSProperties } from "react";

import { color } from "./color";

const BLUR = "blur(20px) saturate(180%)";

/**
 * One frosted layer over a solid canvas. Never stack frost on frost.
 * When reduced transparency is on, return an opaque surface.
 */
export function frostStyle(
  reducedTransparency: boolean,
  weight: "light" | "heavy" | "pane" = "light",
): CSSProperties {
  if (reducedTransparency) {
    return {
      background: color.surface.base,
      backdropFilter: "none",
      WebkitBackdropFilter: "none",
    };
  }
  const fill =
    weight === "pane"
      ? color.surface.frostPane
      : weight === "heavy"
        ? color.surface.frostHeavy
        : color.surface.frost;
  return {
    background: fill,
    backdropFilter: BLUR,
    WebkitBackdropFilter: BLUR,
  };
}
