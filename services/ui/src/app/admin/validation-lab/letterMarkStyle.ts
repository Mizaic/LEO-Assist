/**
 * Hardcoded mark colours: fill is kind, bar is context.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836 / VT-F0A6B9F4
 */

export interface MarkStyle {
  bg: string;
  fg: string;
  label: string;
  bar?: string;
}

export const CONTEXT_BAR_PX = 8;

export const ASSERTION_STYLE: Record<string, MarkStyle> = {
  present: { bg: "#FDE68A", fg: "#78350F", bar: "#CA8A04", label: "Present" },
  historical: { bg: "#CBD5E1", fg: "#1E293B", bar: "#475569", label: "History" },
  family: { bg: "#C7D2FE", fg: "#312E81", bar: "#4F46E5", label: "Family" },
  absent: { bg: "#FECACA", fg: "#7F1D1D", bar: "#DC2626", label: "Not present" },
  refuted: { bg: "#FECACA", fg: "#7F1D1D", bar: "#DC2626", label: "Refuted" },
  possible: { bg: "#FCD34D", fg: "#78350F", bar: "#D97706", label: "Uncertain" },
  planned: { bg: "#BFDBFE", fg: "#1E3A8A", bar: "#2563EB", label: "Planned" },
  hypothetical: { bg: "#DDD6FE", fg: "#4C1D95", bar: "#7C3AED", label: "Maybe later" },
  declined: { bg: "#FED7AA", fg: "#9A3412", bar: "#EA580C", label: "Declined" },
  cancelled: { bg: "#FED7AA", fg: "#9A3412", bar: "#EA580C", label: "Cancelled" },
};

export const TAG_STYLE: Record<string, MarkStyle> = {
  finding: { bg: "#99F6E4", fg: "#115E59", label: "Finding" },
  disorder: { bg: "#F9A8D4", fg: "#831843", label: "Disorder" },
  situation: { bg: "#FDBA74", fg: "#7C2D12", label: "Situation" },
  procedure: { bg: "#86EFAC", fg: "#14532D", label: "Procedure" },
  observable: { bg: "#67E8F9", fg: "#155E75", label: "Observable" },
  substance: { bg: "#BEF264", fg: "#3F6212", label: "Substance" },
  body_structure: { bg: "#D6D3D1", fg: "#44403C", label: "Body part" },
  qualifier_value: { bg: "#E879F9", fg: "#701A75", label: "Qualifier" },
};

const OTHER_STYLE: MarkStyle = { bg: "#E2E8F0", fg: "#334155", label: "Other" };

export const LEGEND_WHEN_KEYS = [
  "present",
  "historical",
  "family",
  "absent",
  "planned",
] as const;

export const LEGEND_WHAT_KEYS = [
  "finding",
  "disorder",
  "situation",
  "procedure",
] as const;

export function semanticTagKey(raw?: string): string {
  return String(raw || "")
    .toLowerCase()
    .replace(/[-\s]+/g, "_")
    .trim();
}

export function semanticTagStyle(raw?: string): MarkStyle | null {
  const key = semanticTagKey(raw);
  if (!key) return null;
  return TAG_STYLE[key] || OTHER_STYLE;
}

export function markFill(tag?: string): MarkStyle {
  return semanticTagStyle(tag) || OTHER_STYLE;
}

export function markBackground(_assertion?: string, tag?: string): string {
  return markFill(tag).bg;
}

export function markForeground(_assertion?: string, tag?: string): string {
  return markFill(tag).fg;
}

export function markContextBar(assertion?: string): string {
  const style = assertionStyle(assertion);
  return style.bar || style.fg;
}

export function assertionKey(raw?: string): string {
  const key = String(raw || "present")
    .toLowerCase()
    .replace(/[_\s]+/g, "");
  return key === "history" ? "historical" : key;
}

export function assertionStyle(raw?: string): MarkStyle {
  const key = assertionKey(raw);
  return ASSERTION_STYLE[key] || ASSERTION_STYLE.present;
}

export function assertionLabel(raw?: string): string {
  return assertionStyle(raw).label;
}

export function semanticTagLabel(raw?: string): string {
  return semanticTagStyle(raw)?.label || "";
}
