// next/font loaders for DM Sans (body) and JetBrains Mono (code, kbd, SNOMED
// IDs only). The CSS variable names must match FONT_VARIABLES exported from
// @leo/design-system/fonts so the design-system tokens resolve at render
// time. See DI-LEO-AI-132.

import { DM_Sans, JetBrains_Mono } from "next/font/google";

export const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-dm-sans",
});

export const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-jetbrains-mono",
});
