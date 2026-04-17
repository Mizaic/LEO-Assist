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
  brand: {
    primary: "#1D4ED8",
    primaryHover: "#1E40AF",
    secondary: "#0EA5E9",
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
