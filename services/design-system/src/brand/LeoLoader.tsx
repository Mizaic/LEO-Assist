/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-47454249
 *   DI: DI-E5FEF0AE
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-47454249")
 */
import { LeoO } from "./LeoLogo";

const SIZE = {
  sm: 22,
  md: 40,
  lg: 56,
} as const;

export type LeoLoaderProps = {
  label?: string;
  size?: keyof typeof SIZE;
  /** stack = centred column for an empty pane; inline = mark beside the caption. */
  layout?: "stack" | "inline";
  variant?: "dark" | "light";
  className?: string;
  style?: React.CSSProperties;
};

export function LeoLoader({
  label,
  size = "md",
  layout = "stack",
  variant = "dark",
  className,
  style,
}: LeoLoaderProps) {
  const stacked = layout === "stack";

  const containerStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: stacked ? "column" : "row",
    alignItems: "center",
    justifyContent: stacked ? "center" : undefined,
    gap: stacked ? 16 : 12,
    ...style,
  };

  return (
    <div
      className={className}
      style={containerStyle}
      role="status"
      aria-live="polite"
      aria-label={label ?? "Loading"}
    >
      <LeoO size={SIZE[size]} variant={variant} spinning title={label ?? "Loading"} />
      {label ? (
        <p style={{ margin: 0, fontSize: 15, color: "var(--leo-color-text-secondary, #475569)" }}>
          {label}
        </p>
      ) : null}
    </div>
  );
}

/** Blank tablet screen used while Shell itself is still suspending. */
export function LeoTabletFallback() {
  return (
    <div
      style={{
        display: "flex",
        minHeight: "100dvh",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--leo-color-bg-default, #F8FAFC)",
      }}
    >
      <LeoLoader size="lg" />
    </div>
  );
}
