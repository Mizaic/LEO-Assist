/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4A8227DD
 *   DI: DI-61CB27B2
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4A8227DD")
 */
// Font CSS variable names for the Mizaic brand font stack.
// Albert Sans (body/UI) and Overpass (headlines) are the Mizaic brand
// typefaces. JetBrains Mono is retained for code, kbd, and SNOMED IDs.
//
// The actual next/font/google loaders are called from the consuming
// Next app's lib/fonts.ts and applied to the <html> element.
// See DI-LEO-AI-132 and services/ui/src/lib/fonts.ts.

export const FONT_VARIABLES = {
  body: "--font-albert-sans",
  heading: "--font-overpass",
  mono: "--font-jetbrains-mono",
} as const;

export const FONT_CONFIG = {
  albertSans: {
    variable: FONT_VARIABLES.body,
    weights: ["300", "400", "500", "600", "700"] as const,
    subsets: ["latin"] as const,
    display: "swap" as const,
  },
  overpass: {
    variable: FONT_VARIABLES.heading,
    weights: ["300", "400", "600", "700"] as const,
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
