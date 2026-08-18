/**
 * Shared look for the clinical complaint door.
 *
 * Atlas: DI-562F2C9E / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
export const glassPanel = {
  bgcolor: "rgba(255,255,255,0.74)",
  backdropFilter: "blur(20px) saturate(180%)",
  WebkitBackdropFilter: "blur(20px) saturate(180%)",
  border: "1px solid",
  borderColor: "rgba(255,255,255,0.55)",
  boxShadow: "0 10px 36px rgba(15, 23, 42, 0.08)",
  borderRadius: "20px",
  "@media (prefers-reduced-transparency: reduce)": {
    bgcolor: "background.paper",
    backdropFilter: "none",
    WebkitBackdropFilter: "none",
    borderColor: "divider",
  },
} as const;

export const pressable = {
  cursor: "pointer",
  transition: "transform 100ms ease-out, box-shadow 160ms ease-out",
  "&:active": { transform: "scale(0.97)" },
  "@media (prefers-reduced-motion: reduce)": {
    transition: "none",
    "&:active": { transform: "none" },
  },
} as const;

export const displayTitle = {
  fontSize: "1.7rem",
  lineHeight: 1.1,
  letterSpacing: "-0.02em",
  fontWeight: 700,
  fontOpticalSizing: "auto",
} as const;

export const sectionLabel = {
  fontSize: "0.78rem",
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase" as const,
  color: "text.secondary",
};

export function statusTone(
  status?: string,
): "success" | "error" | "default" {
  const key = (status || "").toLowerCase();
  if (key === "completed") return "success";
  if (key === "failed") return "error";
  return "default";
}

export function shortDate(value?: string): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function matchLabel(matchedOn?: string): string {
  if (matchedOn === "nhs") return "NHS";
  if (matchedOn === "ubrn") return "Referral";
  if (matchedOn === "name") return "Name";
  if (matchedOn === "letter") return "In letter";
  return "";
}
