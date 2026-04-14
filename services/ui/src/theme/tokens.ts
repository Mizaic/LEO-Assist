/**
 * Design tokens for the LEO Intelligence Console.
 *
 * Centralises spacing, health colours, and typography so every component
 * in the console shares a single visual language.
 */

export const HEALTH_COLORS = {
  healthy: "#2e7d32",       // MUI success.dark
  warning: "#ed6c02",       // MUI warning.main
  error: "#d32f2f",         // MUI error.main
  neutral: "#757575",       // MUI text.secondary
  info: "#0288d1",          // MUI info.main
} as const;

export type HealthStatus = "healthy" | "warning" | "error" | "neutral" | "info";

export const STAGE_COLORS: Record<string, string> = {
  DISCOVER: "#1565c0",
  CURATE:   "#6a1b9a",
  TRAIN:    "#e65100",
  EVALUATE: "#00695c",
  DEPLOY:   "#1b5e20",
  MONITOR:  "#37474f",
};

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

export const FONT_SIZES = {
  label: "0.72rem",
  body: "0.875rem",
  subtitle: "0.9rem",
  title: "1rem",
  heading: "1.125rem",
} as const;
