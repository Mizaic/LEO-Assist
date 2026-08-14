/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
// next/font loaders for the Mizaic brand font stack:
//   Albert Sans  -- body copy and UI chrome (replaces DM Sans)
//   Overpass     -- headlines and display type
//   JetBrains Mono -- code, kbd, SNOMED IDs (unchanged)
//
// CSS variable names must match FONT_VARIABLES in @leo/design-system/fonts
// so that design-system tokens resolve at render time.
// See DI-LEO-AI-132.

import { Albert_Sans, Overpass, JetBrains_Mono } from "next/font/google";

export const albertSans = Albert_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
  variable: "--font-albert-sans",
});

export const overpass = Overpass({
  subsets: ["latin"],
  weight: ["300", "400", "600", "700"],
  display: "swap",
  variable: "--font-overpass",
});

export const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-jetbrains-mono",
});
