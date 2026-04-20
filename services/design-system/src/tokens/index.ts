/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-0AE8E53C
 *   DI: DI-21C63B6A
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-0AE8E53C")
 */
import { color } from "./color";
import { density } from "./density";
import { motion, reducedMotion } from "./motion";
import { elevation, radius, spacing } from "./spacing";
import { typography } from "./typography";

export { color } from "./color";
export { density } from "./density";
export {
  motion,
  reducedMotion,
  type DurationTransition,
  type SpringTransition,
  type MotionTokens,
} from "./motion";
export { elevation, radius, spacing, type SpacingKey } from "./spacing";
export { typography, type TypographyTokens } from "./typography";
export type { ColorTokens } from "./color";
export type { DensityTokens } from "./density";

export const tokens = {
  color,
  density,
  elevation,
  motion,
  radius,
  spacing,
  typography,
} as const;

export type Tokens = typeof tokens;
