// Density tokens. Inherits DI-LEO-AI-119: minimum 44px touch target,
// comfortable default, compact option for data-dense screens.
export const density = {
  touchTargetMin: 44,
  rowHeight: {
    compact: 40,
    comfortable: 48,
    spacious: 56,
  },
  surfacePadding: {
    compact: 16,
    comfortable: 24,
  },
} as const;

export type DensityTokens = typeof density;
