/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4A8227DD
 *   DI: DI-61CB27B2
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4A8227DD")
 */
// Font CSS variable names used across the app. The actual next/font/google
// loaders must be called from the consuming Next app's `app/layout.tsx`,
// then `dmSans.variable` and `jetBrainsMono.variable` should be applied to
// the <html> element so the CSS variables below resolve.
//
// See DI-LEO-AI-132 and services/ui/src/lib/fonts.ts.

export const FONT_VARIABLES = {
  body: "--font-dm-sans",
  mono: "--font-jetbrains-mono",
} as const;

export const FONT_CONFIG = {
  dmSans: {
    variable: FONT_VARIABLES.body,
    weights: ["400", "500", "600", "700"] as const,
    subsets: ["latin"] as const,
    display: "swap" as const,
  },
  jetBrainsMono: {
    variable: FONT_VARIABLES.mono,
    weights: ["400", "500"] as const,
    subsets: ["latin"] as const,
    display: "swap" as const,
  },
} as const;

export type FontConfig = typeof FONT_CONFIG;
