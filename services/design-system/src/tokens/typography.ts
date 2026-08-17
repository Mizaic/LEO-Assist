/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
// Typography scale. Albert Sans (body) and Overpass (headlines) are the
// Mizaic brand fonts. Both are loaded by the consuming Next app through
// next/font and exposed as --font-albert-sans / --font-overpass CSS
// variables. JetBrains Mono is retained for code/kbd/SNOMED IDs.
// See DI-LEO-AI-132.
export const typography = {
  fontFamily: {
    body: "var(--font-albert-sans), 'Albert Sans', -apple-system, system-ui, sans-serif",
    heading: "var(--font-overpass), 'Overpass', -apple-system, system-ui, sans-serif",
    mono: "var(--font-jetbrains-mono), 'JetBrains Mono', 'Menlo', monospace",
  },
  fontSize: {
    caption: 12,
    small: 14,
    body: 16,
    subtitle: 20,
    h3: 24,
    h2: 32,
    h1: 40,
  },
  lineHeight: {
    body: 1.45,
    display: 1.2,
  },
  fontWeight: {
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
  /* Size-specific tracking. Large display tightens; captions open slightly. */
  letterSpacing: {
    display: "-0.02em",
    body: "0em",
    caption: "0.02em",
  },
} as const;

export type TypographyTokens = typeof typography;
