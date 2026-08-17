/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
// Semantic colour tokens. WCAG 2.1 AA safe when used against the intended
// surface. See DI-LEO-AI-130 and the existing theme mapping rules.
export const color = {
  surface: {
    base: "#FFFFFF",
    alt: "#F8FAFC",
    raised: "#FFFFFF",
    divider: "#E2E8F0",
    overlay: "rgba(15, 23, 42, 0.45)",
    /* Page ground -- blue-grey so white cards and frost can separate. */
    canvas: "#D8E0EE",
    /* Frosted chrome -- one translucent layer over canvas, never over frost. */
    frost: "rgba(248, 250, 253, 0.78)",
    frostHeavy: "rgba(232, 238, 248, 0.9)",
    /* White glass pane -- sits on canvas, never on another frost. */
    frostPane: "rgba(255, 255, 255, 0.88)",
  },
  text: {
    primary: "#0F172A",
    secondary: "#596577",
    disabled: "#94A3B8",
    inverse: "#FFFFFF",
    caption: "#6B7280",
  },
  /* -- Mizaic brand palette -- */
  brand: {
    /* Electric Blue: contrast 6.02:1 on white -- WCAG AA compliant */
    primary: "#0d46d6",
    primaryHover: "#002178",
    primaryDark: "#00093b",
    secondary: "#9338ff",
    secondaryHover: "#6600ab",
    accent: "#d758ff",
    onBrand: "#FFFFFF",
  },
  status: {
    success: "#047857",
    warning: "#B45309",
    danger: "#B91C1C",
    info: "#0d46d6",
    neutral: "#475569",
  },
  focus: {
    ring: "#0d46d6",
    ringAlpha: "rgba(13, 70, 214, 0.35)",
  },
  /* Data-viz series -- distinct from brand/UI chrome conceptually. */
  chart: {
    seriesPrimary: "#0d46d6",
  },
} as const;

export type ColorTokens = typeof color;
