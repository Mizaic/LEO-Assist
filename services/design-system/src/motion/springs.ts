/**
 * Apple-style spring presets (WWDC 2018 Designing Fluid Interfaces).
 *
 * bounce 0 ~= damping 1.0 (critically damped). Use for chrome.
 * bounce 0.2 ~= damping 0.8. Use only after a flick / throw.
 * duration here is response, not a fixed timeline -- settle time emerges.
 *
 * Atlas trace:
 *   DO: DO-6DCC699A
 *   DI: DI-9DDC5471
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-6DCC699A")
 */
export const springs = {
  ui: { type: "spring" as const, bounce: 0, duration: 0.35 },
  flick: { type: "spring" as const, bounce: 0.2, duration: 0.3 },
  press: { type: "spring" as const, bounce: 0, duration: 0.18 },
};

export const PRESS_SCALE = 0.97;

export function springOrInstant(
  reducedMotion: boolean,
  spring = springs.ui,
): { duration: number } | typeof springs.ui | typeof springs.flick | typeof springs.press {
  return reducedMotion ? { duration: 0 } : spring;
}

export function tapScale(reducedMotion: boolean, scale = PRESS_SCALE) {
  if (reducedMotion) return undefined;
  return { scale };
}
