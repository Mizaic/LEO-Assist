/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BCA9B190")
 */
"use client";

import { motion as fm } from "framer-motion";
import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";

/** Slow breathing cycle -- roughly one calm inhale/exhale. */
const BREATH_CYCLE_S = 4;

/**
 * Indeterminate fill for ProgressStrip. Uses a gentle opacity pulse
 * (mindfulness breathing pace) instead of horizontal motion.
 */
export function ProgressStripScanner({
  reducedMotion,
}: {
  reducedMotion: boolean;
}) {
  return (
    <fm.span
      aria-hidden="true"
      data-testid="progress-strip-indeterminate"
      animate={
        reducedMotion ? { opacity: 0.55 } : { opacity: [0.32, 0.72, 0.32] }
      }
      transition={
        reducedMotion
          ? { duration: 0 }
          : {
              duration: BREATH_CYCLE_S,
              repeat: Infinity,
              ease: "easeInOut",
            }
      }
      style={{
        position: "absolute",
        inset: 0,
        background: color.brand.primary,
        borderRadius: radius.pill,
      }}
    />
  );
}
