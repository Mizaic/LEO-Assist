/**
 * Locked LEO-by-Mizaic brand tokens for the SDK trust boundary.
 *
 * Atlas trace:
 *   DI: DI-85944331 (locked branding plus reactive light/dark mode)
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-85944331")
 *
 * IMMUTABILITY CONTRACT: nothing in this file is exposed as a CSS
 * custom property the host can override. The values below are
 * compiled into the shadow stylesheet and the iframe stylesheet at
 * build time. The only host-driven variation is light vs dark via
 * prefers-color-scheme, which is implemented inside the SDK by
 * matching media queries inside the shadow root and choosing
 * between BRAND.light and BRAND.dark.
 *
 * The SBAR stage palette mirrors the NHS SBAR communication-training
 * colours used by services/ui/src/components/sbar-final/SbarFinalView
 * (STAGE_THEME), keeping the LEO surface visually identical inside a
 * Mizaic host or inside the LEO admin app.
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
  warningBg: string;
  warningInk: string;
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

export const BRAND = Object.freeze({
  productName: "LEO by Mizaic",
  fontFamily:
    "Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif",
  light: Object.freeze({
    background: "#ffffff",
    surface: "#ffffff",
    surfaceMuted: "#f8fafc",
    border: "#e2e8f0",
    text: "#0f172a",
    textMuted: "#475569",
    primary: "#1e3a8a",
    primaryInk: "#ffffff",
    warningBg: "#fef3c7",
    warningInk: "#92400e",
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
    warningBg: "#78350f",
    warningInk: "#fde68a",
  } satisfies BrandSurface),
} as const);

/**
 * Inline SVG for the Mizaic mark used inside the widget header. Kept
 * as a string so it ships with the bundle and never depends on a host
 * fetch (and so a host cannot blackhole the asset to hide the brand).
 */
export const MIZAIC_MARK_SVG: string =
  '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"' +
  ' role="img" aria-label="LEO by Mizaic">' +
  '<rect width="64" height="64" rx="14" fill="currentColor"/>' +
  '<text x="32" y="40" text-anchor="middle"' +
  ' font-family="Inter, system-ui, sans-serif" font-weight="700"' +
  ' font-size="22" fill="#ffffff">LEO</text>' +
  "</svg>";
