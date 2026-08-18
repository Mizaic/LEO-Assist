/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-47454249
 *   DI: DI-E5FEF0AE
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-47454249")
 */
import "./leo-logo.css";

/** Official LEO wordmark paths (Mizaic brand SVG, viewBox 116x45). */
const PATHS = {
  l: "M9.05719 1.34375H0V44.3562H26.9734L29.7162 36.8751H9.05719V1.34375Z",
  e: "M36.4746 44.3556V1.44336H66.6363L63.901 8.92445H45.5318V19.1495H60.4371V26.6306H45.5318V36.8764H66.7194L63.969 44.3575H36.4746V44.3556Z",
  accent:
    "M99.8359 10.9118C102.224 12.2564 104.051 14.3252 105.352 16.8763L114.383 14.5635C112.344 9.11531 108.385 4.87931 103.064 2.21289L99.8359 10.9118Z",
  ring: "M106.508 20.9663C106.547 21.3824 106.577 22.1104 106.577 22.5378C106.577 29.8809 100.675 35.798 93.3446 35.798C86.0147 35.798 80.0722 29.8449 80.0722 22.5019C80.0722 15.1588 86.0147 9.20575 93.3446 9.20575C94.2281 9.20575 95.0889 9.29652 95.9232 9.46104L98.6623 0.601362C96.8992 0.156959 95.2437 0 93.3446 0C80.9406 0 70.8848 10.0738 70.8848 22.5C70.8848 34.9262 80.9406 45 93.3446 45C105.749 45 115.805 34.9262 115.805 22.5C115.805 21.3899 115.721 20.2988 115.567 19.2322L106.509 20.9644L106.508 20.9663Z",
};

/* -- Mizaic brand palette -- */
const PALETTE = {
  dark: {
    letter: "#C5C8D0",
    ring: "#FFFFFF",
    accent: "#d758ff",
  },
  light: {
    letter: "#00093B",
    ring: "#00093B",
    accent: "#d758ff",
  },
} as const;

type ResolvedColors = {
  letter: string;
  ring: string;
  accent: string;
};

function cx(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(" ");
}

function OGroup({
  spinning,
  ring,
  accent,
}: {
  spinning: boolean;
  ring: string;
  accent: string;
}) {
  return (
    <g className={spinning ? "leo-logo-spin" : undefined}>
      <path d={PATHS.ring} fill={ring} />
      <path d={PATHS.accent} fill={accent} />
    </g>
  );
}

export type LeoLogoProps = {
  className?: string;
  /** Rendered height in pixels. Width follows the 116x45 wordmark aspect ratio. */
  height?: number;
  /** Colour scheme for the wordmark. Use "dark" on dark surfaces, "light" on light. */
  variant?: "dark" | "light";
  /** Rotate the O -- starting with the magenta accent at top-right. */
  spinning?: boolean;
  /** Seconds per full turn when spinning. */
  spinDuration?: number;
  letterColor?: string;
  ringColor?: string;
  accentColor?: string;
  title?: string;
};

function resolvePalette(
  variant: "dark" | "light",
  letterColor?: string,
  ringColor?: string,
  accentColor?: string,
): ResolvedColors {
  const palette = PALETTE[variant];
  return {
    letter: letterColor ?? palette.letter,
    ring: ringColor ?? palette.ring,
    accent: accentColor ?? palette.accent,
  };
}

export function LeoLogo({
  className,
  height = 72,
  variant = "dark",
  spinning = true,
  spinDuration = 1.8,
  letterColor,
  ringColor,
  accentColor,
  title = "LEO",
}: LeoLogoProps) {
  const colors = resolvePalette(variant, letterColor, ringColor, accentColor);
  const width = (height * 116) / 45;

  return (
    <svg
      className={cx("leo-logo", className)}
      width={width}
      height={height}
      viewBox="0 0 116 45"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={title}
      style={{ ["--leo-spin-duration" as string]: `${spinDuration}s` }}
    >
      <title>{title}</title>
      <path d={PATHS.l} fill={colors.letter} />
      <path d={PATHS.e} fill={colors.letter} />
      <OGroup spinning={spinning} ring={colors.ring} accent={colors.accent} />
    </svg>
  );
}

export type LeoOProps = {
  className?: string;
  size?: number;
  variant?: "dark" | "light";
  spinning?: boolean;
  spinDuration?: number;
  ringColor?: string;
  accentColor?: string;
  title?: string;
};

/** Cropped spinning O -- the in-app loading mark, without the full wordmark. */
export function LeoO({
  className,
  size = 32,
  variant = "dark",
  spinning = true,
  spinDuration = 1.8,
  ringColor,
  accentColor,
  title = "Loading",
}: LeoOProps) {
  const colors = resolvePalette(variant, undefined, ringColor, accentColor);

  return (
    <svg
      className={cx("leo-o", className)}
      width={size}
      height={size}
      viewBox="70.8848 0 44.9202 45"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={title}
      style={{ ["--leo-spin-duration" as string]: `${spinDuration}s` }}
    >
      <title>{title}</title>
      <OGroup spinning={spinning} ring={colors.ring} accent={colors.accent} />
    </svg>
  );
}
