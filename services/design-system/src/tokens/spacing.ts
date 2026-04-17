// Strict 8pt grid. See DI-LEO-AI-130.
export const spacing = {
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  xxxl: 64,
} as const;

export type SpacingKey = keyof typeof spacing;

export const radius = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  pill: 999,
} as const;

export const elevation = {
  none: "none",
  card: "0 1px 2px rgba(15, 23, 42, 0.06), 0 1px 3px rgba(15, 23, 42, 0.08)",
  popover:
    "0 8px 16px rgba(15, 23, 42, 0.08), 0 2px 4px rgba(15, 23, 42, 0.06)",
  modal: "0 24px 48px rgba(15, 23, 42, 0.18)",
} as const;
