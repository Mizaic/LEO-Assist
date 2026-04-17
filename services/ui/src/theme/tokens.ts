/**
 * Design tokens for the LEO Intelligence Console.
 *
 * Single source of truth for spacing, typography, motion, focus, radius,
 * contrast pairs, and density tiers. Consumed by theme.ts (MUI) and by
 * theme/tokens.css (CSS custom properties for non-MUI DOM).
 *
 * See DI-LEO-AI-118 (tokens) and DI-LEO-AI-119 (density).
 */

export const HEALTH_COLORS = {
  healthy: "#2e7d32",
  warning: "#b45309",
  error: "#b91c1c",
  neutral: "#4b5563",
  info: "#0277bd",
} as const;

export type HealthStatus = "healthy" | "warning" | "error" | "neutral" | "info";

export const STAGE_COLORS: Record<string, string> = {
  DISCOVER: "#1565c0",
  CURATE: "#6a1b9a",
  TRAIN: "#e65100",
  EVALUATE: "#00695c",
  DEPLOY: "#1b5e20",
  MONITOR: "#37474f",
};

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const FONT_SIZES = {
  label: "0.8125rem",
  body: "1rem",
  subtitle: "1rem",
  title: "1.125rem",
  heading: "1.25rem",
} as const;

export const TYPE_SCALE = {
  h1: { fontSize: "2rem", fontWeight: 700, lineHeight: 1.2, letterSpacing: "-0.01em" },
  h2: { fontSize: "1.5rem", fontWeight: 700, lineHeight: 1.25, letterSpacing: "-0.01em" },
  h3: { fontSize: "1.25rem", fontWeight: 600, lineHeight: 1.3 },
  h4: { fontSize: "1.125rem", fontWeight: 700, lineHeight: 1.35, letterSpacing: "-0.01em" },
  h5: { fontSize: "1rem", fontWeight: 700, lineHeight: 1.4, letterSpacing: "-0.01em" },
  h6: { fontSize: "0.95rem", fontWeight: 600, lineHeight: 1.4 },
  body1: { fontSize: "1rem", fontWeight: 400, lineHeight: 1.55 },
  body2: { fontSize: "0.95rem", fontWeight: 400, lineHeight: 1.5 },
  caption: { fontSize: "0.8125rem", fontWeight: 400, lineHeight: 1.45 },
} as const;

export const RADIUS = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  full: 9999,
} as const;

export const MOTION = {
  durationFast: 120,
  durationNormal: 200,
  durationSlow: 320,
  easingStandard: "cubic-bezier(0.4, 0, 0.2, 1)",
  easingEmphasised: "cubic-bezier(0.2, 0, 0, 1)",
} as const;

export const FOCUS_RING = {
  widthPx: 3,
  offsetPx: 2,
  color: "#1F3A8A",
} as const;

export type DensityTier = "compact" | "comfortable" | "spacious";

export const DENSITY_MAP: Record<
  DensityTier,
  { minHeightPx: number; paddingYPx: number; paddingXPx: number; fontSizeRem: number }
> = {
  compact: { minHeightPx: 32, paddingYPx: 4, paddingXPx: 10, fontSizeRem: 0.875 },
  comfortable: { minHeightPx: 40, paddingYPx: 8, paddingXPx: 14, fontSizeRem: 1 },
  spacious: { minHeightPx: 48, paddingYPx: 12, paddingXPx: 18, fontSizeRem: 1.0625 },
} as const;

/**
 * Contrast pairs that have been validated against WCAG 2.1 AA.
 * role = "normal" requires >= 4.5:1. role = "large" or "non-text" requires >= 3:1.
 */
export type ContrastRole = "normal" | "large" | "non-text";

export interface ContrastPair {
  name: string;
  fg: string;
  bg: string;
  role: ContrastRole;
}

export const CONTRAST_PAIRS: ContrastPair[] = [
  { name: "body-on-default", fg: "#0F172A", bg: "#F8FAFC", role: "normal" },
  { name: "body-on-paper", fg: "#0F172A", bg: "#FFFFFF", role: "normal" },
  { name: "secondary-on-default", fg: "#475569", bg: "#F8FAFC", role: "normal" },
  { name: "caption-on-default", fg: "#4b5563", bg: "#F8FAFC", role: "normal" },
  { name: "primary-on-white", fg: "#1F3A8A", bg: "#FFFFFF", role: "normal" },
  { name: "error-on-white", fg: "#b91c1c", bg: "#FFFFFF", role: "normal" },
  { name: "warning-on-white", fg: "#b45309", bg: "#FFFFFF", role: "normal" },
  { name: "success-on-white", fg: "#15803d", bg: "#FFFFFF", role: "normal" },
  { name: "focus-ring-on-default", fg: "#1F3A8A", bg: "#F8FAFC", role: "non-text" },
  { name: "divider-on-default", fg: "#64748b", bg: "#F8FAFC", role: "non-text" },
];

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const full =
    clean.length === 3
      ? clean
          .split("")
          .map((c) => c + c)
          .join("")
      : clean;
  const num = parseInt(full, 16);
  return [(num >> 16) & 0xff, (num >> 8) & 0xff, num & 0xff];
}

function channelLuminance(channel: number): number {
  const c = channel / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return (
    0.2126 * channelLuminance(r) +
    0.7152 * channelLuminance(g) +
    0.0722 * channelLuminance(b)
  );
}

export function computeContrastRatio(fg: string, bg: string): number {
  const l1 = relativeLuminance(fg);
  const l2 = relativeLuminance(bg);
  const [light, dark] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (light + 0.05) / (dark + 0.05);
}

export const PATIENT_REACHABLE_PREFIXES = [
  "/portal",
  "/mail",
  "/safety-netting",
  "/games",
  "/care/wellbeing",
  "/sign-in",
] as const;

export function isPatientReachableRoute(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return PATIENT_REACHABLE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/"),
  );
}
