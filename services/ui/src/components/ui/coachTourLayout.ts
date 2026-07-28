/**
 * Viewport layout helpers for CoachTour (spotlight cut-out + bubble).
 *
 * Atlas trace: DI-LEO-AI-121 / DO-9539333E
 */

export const BUBBLE_MAX_WIDTH = 320;
export const BUBBLE_EST_HEIGHT = 200;
export const VIEWPORT_PAD = 8;
export const SPOTLIGHT_PAD = 6;

export function measureAnchor(selector: string): DOMRect | null {
  if (typeof document === "undefined") return null;
  const el = document.querySelector(selector);
  if (!(el instanceof HTMLElement)) return null;
  if (typeof el.scrollIntoView === "function") {
    el.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
  return el.getBoundingClientRect();
}

/** Viewport coords for position:fixed so sticky chrome cannot cover the bubble. */
export function bubblePosition(rect: DOMRect | null): { top: number; left: number } {
  if (!rect) return { top: VIEWPORT_PAD, left: VIEWPORT_PAD };
  const spaceBelow = window.innerHeight - rect.bottom - VIEWPORT_PAD;
  const top =
    spaceBelow >= BUBBLE_EST_HEIGHT
      ? rect.bottom + VIEWPORT_PAD + SPOTLIGHT_PAD
      : Math.max(VIEWPORT_PAD, rect.top - BUBBLE_EST_HEIGHT - VIEWPORT_PAD);
  const left = Math.max(
    VIEWPORT_PAD,
    Math.min(rect.left, window.innerWidth - BUBBLE_MAX_WIDTH - VIEWPORT_PAD),
  );
  return { top, left };
}

export function spotlightBox(rect: DOMRect | null): {
  top: number;
  left: number;
  width: number;
  height: number;
} | null {
  if (!rect) return null;
  return {
    top: Math.max(0, rect.top - SPOTLIGHT_PAD),
    left: Math.max(0, rect.left - SPOTLIGHT_PAD),
    width: rect.width + SPOTLIGHT_PAD * 2,
    height: rect.height + SPOTLIGHT_PAD * 2,
  };
}
