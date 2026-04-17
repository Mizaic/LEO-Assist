// Typography scale. DM Sans is loaded by the consuming Next app through
// next/font and exposed as the --font-dm-sans CSS variable.
// See DI-LEO-AI-132.
export const typography = {
  fontFamily: {
    body: "var(--font-dm-sans), 'DM Sans', -apple-system, system-ui, sans-serif",
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
} as const;

export type TypographyTokens = typeof typography;
