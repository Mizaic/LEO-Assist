/**
 * Shared framer-motion presets for the Clinical Guidelines tab and the
 * rule-logic builder dialog (EditRuleDialog/).
 *
 * Cosmetic only -- no logic or safety-relevant behaviour lives here. All
 * presets accept a `reducedMotion` flag (from `useMotion()` in
 * @leo/design-system) and collapse to an instant, opacity-only transition
 * when true, so `prefers-reduced-motion` is always honoured.
 */

import type { Transition, Variants } from "framer-motion";

const BOUNCY_SPRING: Transition = {
  type: "spring",
  stiffness: 420,
  damping: 22,
  mass: 0.8,
};

const REDUCED: Transition = { duration: 0 };

/** Bouncy pop-in used for cards, chips, and dialog surfaces. */
export function popSpring(reducedMotion: boolean, delay = 0): Transition {
  if (reducedMotion) return REDUCED;
  return { ...BOUNCY_SPRING, delay };
}

/** Caps stagger delay so long lists don't take forever to finish animating. */
export function staggerDelay(index: number, step = 0.05, max = 20): number {
  return Math.min(index, max) * step;
}

/** Entrance variants for a list item that pops and slides up into place. */
export function popVariants(reducedMotion: boolean): Variants {
  if (reducedMotion) {
    return { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } };
  }
  return {
    initial: { opacity: 0, y: 10, scale: 0.94 },
    animate: { opacity: 1, y: 0, scale: 1 },
    exit: { opacity: 0, scale: 0.92, transition: { duration: 0.12 } },
  };
}

/** Slide variants for step-canvas transitions, direction-aware. */
export function slidePanelVariants(reducedMotion: boolean, direction: 1 | -1): Variants {
  if (reducedMotion) {
    return { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } };
  }
  return {
    initial: { opacity: 0, x: 24 * direction },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: -24 * direction, transition: { duration: 0.15 } },
  };
}

/** Springy hover/tap scale for buttons and pills that invite interaction. */
export function bounceInteraction(reducedMotion: boolean) {
  if (reducedMotion) return {};
  return {
    whileHover: { scale: 1.04 },
    whileTap: { scale: 0.96 },
    transition: BOUNCY_SPRING,
  };
}

/** Looping pulse/glow used for celebratory "it's live" moments. */
export function celebrationPulse(reducedMotion: boolean) {
  if (reducedMotion) return {};
  return {
    animate: { scale: [1, 1.08, 1], boxShadow: [
      "0 0 0 rgba(20,184,166,0)",
      "0 0 16px rgba(20,184,166,0.55)",
      "0 0 0 rgba(20,184,166,0)",
    ] },
    transition: { duration: 1.1, repeat: 2, ease: "easeInOut" },
  };
}
