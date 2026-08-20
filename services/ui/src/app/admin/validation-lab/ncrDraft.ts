/**
 * Product NCR draft helpers for Validation Lab.
 *
 * Atlas: DI-287FFFD0
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
export const NCR_SEVERITIES = [
  "catastrophic",
  "major",
  "minor",
  "cosmetic",
] as const;

export const NCR_OPEN_STATUSES = [
  "identified",
  "contained",
  "investigated",
  "disposition_pending",
] as const;

export const NCR_CLOSED_STATUSES = ["closed", "cancelled", "canceled"] as const;

export type NcrSeverity = (typeof NCR_SEVERITIES)[number];

export interface ProductNcr {
  id: string;
  title: string;
  description: string;
  severity: string;
  status: string;
  created_at: string;
  product_id: string;
}

export interface NcrDraft {
  title: string;
  description: string;
  severity: NcrSeverity;
}

export function emptyNcrDraft(): NcrDraft {
  return { title: "", description: "", severity: "minor" };
}

export function isOpenNcr(row: ProductNcr): boolean {
  const status = (row.status || "").trim().toLowerCase();
  return !(NCR_CLOSED_STATUSES as readonly string[]).includes(status);
}

export function filterProductNcrs(rows: ProductNcr[], query: string): ProductNcr[] {
  const needle = query.trim().toLowerCase();
  if (needle) {
    const exact = rows.filter((row) => row.id.toLowerCase() === needle);
    if (exact.length) return exact;
  }
  const open = rows.filter(isOpenNcr);
  if (!needle) return open;
  return open.filter((row) => ncrHaystack(row).includes(needle));
}

export function visibleProductNcrs(rows: ProductNcr[], cap = 40): ProductNcr[] {
  return rows.slice(0, Math.max(1, cap));
}

export function ncrDraftError(draft: NcrDraft): string {
  if (draft.title.trim().length < 5) {
    return "Title needs at least five characters.";
  }
  if (draft.description.trim().length < 5) {
    return "Say what went wrong in at least five characters.";
  }
  if (!NCR_SEVERITIES.includes(draft.severity)) {
    return "Pick how serious this is.";
  }
  return "";
}

function ncrHaystack(row: ProductNcr): string {
  return [row.title, row.description, row.id, row.status, row.severity]
    .join(" ")
    .toLowerCase();
}
