/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
// Motion tokens. Consumed by the motion layer (MotionProvider / useMotion).
// Durations are in milliseconds so they align with both CSS transitions and
// framer-motion transition objects. See DI-LEO-AI-131.

export interface DurationTransition {
  duration: number;
  ease?: [number, number, number, number] | string;
}

export interface SpringTransition {
  duration: number;
  type: "spring";
  mass: number;
  stiffness: number;
  damping: number;
}

export const motion = {
  default: {
    duration: 180,
    ease: "easeOut",
  } as DurationTransition,
  route: {
    duration: 220,
    type: "spring",
    mass: 0.9,
    stiffness: 210,
    damping: 28,
  } as SpringTransition,
  hover: {
    duration: 120,
    ease: "easeOut",
  } as DurationTransition,
  instant: { duration: 0 } as DurationTransition,
} as const;

export type MotionTokens = typeof motion;

// Returns transitions with durations collapsed to 0 for reduced-motion users.
export function reducedMotion(
  source: MotionTokens = motion,
): {
  default: DurationTransition;
  route: SpringTransition;
  hover: DurationTransition;
  instant: DurationTransition;
} {
  return {
    default: { ...source.default, duration: 0 },
    route: { ...source.route, duration: 0 },
    hover: { ...source.hover, duration: 0 },
    instant: { ...source.instant, duration: 0 },
  };
}
