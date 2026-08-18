/**
 * Locked LEO-by-Mizaic brand tokens for the SDK trust boundary.
 *
 * Atlas trace:
 *   DI: DI-E5FEF0AE (Mizaic brand tokens, fonts, and wordmark)
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-E5FEF0AE")
 *
 * IMMUTABILITY CONTRACT: nothing in this file is exposed as a CSS
 * custom property the host can override. Values are compiled into
 * the shadow and iframe stylesheets at build time.
 *
 * SBAR stage colours stay on the NHS SBAR training palette used by
 * SbarFinalView.STAGE_THEME. Those are scan colours, not brand chrome.
 */

export interface BrandSurface {
  background: string;
  surface: string;
  surfaceMuted: string;
  border: string;
  text: string;
  textMuted: string;
  primary: string;
  primaryInk: string;
  markInk: string;
  warningBg: string;
  warningInk: string;
  infoBorder: string;
  infoBg: string;
  infoInk: string;
}

export interface StageTheme {
  accent: string;
  tint: string;
  ink: string;
}

export const STAGE_THEME: Readonly<
  Record<"situation" | "background" | "assessment" | "recommendation", StageTheme>
> = Object.freeze({
  situation: Object.freeze({ accent: "#2563eb", tint: "#eff6ff", ink: "#1e3a8a" }),
  background: Object.freeze({ accent: "#7c3aed", tint: "#f5f3ff", ink: "#5b21b6" }),
  assessment: Object.freeze({ accent: "#d97706", tint: "#fffbeb", ink: "#92400e" }),
  recommendation: Object.freeze({ accent: "#0d9488", tint: "#f0fdfa", ink: "#115e59" }),
});

const FONT_BODY =
  '"Albert Sans", system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
const FONT_HEADING =
  '"Overpass", "Albert Sans", system-ui, -apple-system, Segoe UI, sans-serif';

export const BRAND = Object.freeze({
  productName: "LEO by Mizaic",
  fontFamily: FONT_BODY,
  fontFamilyHeading: FONT_HEADING,
  light: Object.freeze({
    background: "#ffffff",
    surface: "#ffffff",
    surfaceMuted: "#f8fafc",
    border: "#e2e8f0",
    text: "#0f172a",
    textMuted: "#475569",
    primary: "#0d46d6",
    primaryInk: "#ffffff",
    markInk: "#00093b",
    warningBg: "#fef3c7",
    warningInk: "#92400e",
    infoBorder: "#0d46d6",
    infoBg: "#e8effc",
    infoInk: "#002178",
  } satisfies BrandSurface),
  dark: Object.freeze({
    background: "#0f172a",
    surface: "#111827",
    surfaceMuted: "#1f2937",
    border: "#374151",
    text: "#f8fafc",
    textMuted: "#cbd5f5",
    primary: "#60a5fa",
    primaryInk: "#0b1120",
    markInk: "#ffffff",
    warningBg: "#78350f",
    warningInk: "#fde68a",
    infoBorder: "#0d46d6",
    infoBg: "#00093b",
    infoInk: "#bfdbfe",
  } satisfies BrandSurface),
} as const);

const RING =
  "M106.508 20.9663C106.547 21.3824 106.577 22.1104 106.577 22.5378C106.577 29.8809 100.675 35.798 93.3446 35.798C86.0147 35.798 80.0722 29.8449 80.0722 22.5019C80.0722 15.1588 86.0147 9.20575 93.3446 9.20575C94.2281 9.20575 95.0889 9.29652 95.9232 9.46104L98.6623 0.601362C96.8992 0.156959 95.2437 0 93.3446 0C80.9406 0 70.8848 10.0738 70.8848 22.5C70.8848 34.9262 80.9406 45 93.3446 45C105.749 45 115.805 34.9262 115.805 22.5C115.805 21.3899 115.721 20.2988 115.567 19.2322L106.509 20.9644L106.508 20.9663Z";
const ACCENT =
  "M99.8359 10.9118C102.224 12.2564 104.051 14.3252 105.352 16.8763L114.383 14.5635C112.344 9.11531 108.385 4.87931 103.064 2.21289L99.8359 10.9118Z";

/** Inline LeoO mark. Ring uses currentColor so light/dark can restyle it. */
export const MIZAIC_MARK_SVG: string =
  '<svg viewBox="70.8848 0 44.9202 45" xmlns="http://www.w3.org/2000/svg"' +
  ' role="img" aria-label="LEO by Mizaic">' +
  `<path d="${RING}" fill="currentColor"/>` +
  `<path d="${ACCENT}" fill="#d758ff"/>` +
  "</svg>";
