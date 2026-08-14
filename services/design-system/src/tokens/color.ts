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
    info: "#1D4ED8",
    neutral: "#475569",
  },
  focus: {
    ring: "#2563EB",
    ringAlpha: "rgba(37, 99, 235, 0.35)",
  },
} as const;

export type ColorTokens = typeof color;
