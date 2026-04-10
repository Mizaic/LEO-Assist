/**
 * Plain English label mappings for Mission Control.
 *
 * Single source of truth: database values MUST NOT appear directly
 * in any rendered UI label. All display text comes from this file.
 */

// -- Episode status labels --

export const EPISODE_STATUS_LABELS: Record<string, string> = {
  completed: "Confirmed cancer",
  closed_benign: "No cancer found",
  stale_no_diagnosis: "No diagnosis after wait",
  stale_post_specialist: "Specialist seen, no diagnosis",
  closed_related: "Duplicate pathway closed",
  in_progress: "Still being investigated",
  merged: "Merged pathway",
  closed_phantom: "Removed (no evidence)",
};

export function getStatusLabel(status: string): string {
  return EPISODE_STATUS_LABELS[status] ?? status;
}

// -- Cancer type labels --

export const CANCER_TYPE_LABELS: Record<string, string> = {
  colorectal: "Bowel (colorectal)",
  lower_gi: "Lower gut",
  upper_gi: "Upper gut",
  lung: "Lung",
  breast: "Breast",
  prostate: "Prostate",
  skin: "Skin",
  gynaecological: "Gynaecological",
  haematological: "Blood cancer",
  head_and_neck: "Head and neck",
  urological: "Urological",
  cns: "Brain and nervous system",
  sarcoma: "Bone and soft tissue",
  non_site_specific: "Type not yet confirmed",
  unknown: "Unknown type",
};

export function getCancerTypeLabel(cancerType: string): string {
  return CANCER_TYPE_LABELS[cancerType] ?? cancerType;
}

// -- Closure reason labels (subset of status used as filter options) --

export const CLOSURE_REASON_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "closed_benign", label: "No cancer found" },
  { value: "stale_no_diagnosis", label: "No diagnosis after wait" },
  { value: "stale_post_specialist", label: "Specialist seen, no diagnosis" },
  { value: "closed_related", label: "Duplicate pathway closed" },
];

// -- Cancer type filter options --

export const CANCER_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "colorectal", label: "Bowel (colorectal)" },
  { value: "lung", label: "Lung" },
  { value: "breast", label: "Breast" },
  { value: "prostate", label: "Prostate" },
  { value: "gynaecological", label: "Gynaecological" },
  { value: "haematological", label: "Blood cancer" },
  { value: "upper_gi", label: "Upper gut" },
  { value: "lower_gi", label: "Lower gut" },
  { value: "head_and_neck", label: "Head and neck" },
  { value: "skin", label: "Skin" },
  { value: "urological", label: "Urological" },
  { value: "cns", label: "Brain and nervous system" },
  { value: "sarcoma", label: "Bone and soft tissue" },
  { value: "non_site_specific", label: "Type not yet confirmed" },
];

// -- Status colour semantics --

export type StatusColour = "success" | "warning" | "error" | "default";

export function getStatusColour(status: string): StatusColour {
  switch (status) {
    case "completed":
      return "success";
    case "in_progress":
      return "warning";
    case "closed_benign":
    case "stale_no_diagnosis":
    case "stale_post_specialist":
    case "closed_related":
      return "default";
    default:
      return "default";
  }
}

// -- Diagnostic interval thresholds (NCDA) --

export type IntervalColour = "success" | "warning" | "error";

export function getDiagnosticIntervalColour(days: number | null | undefined): IntervalColour {
  if (days == null) return "success";
  if (days <= 28) return "success";
  if (days <= 62) return "warning";
  return "error";
}

// -- Review status display --

export function getReviewLabel(reviewedBy: string | null | undefined): string {
  if (!reviewedBy) return "Needs review";
  return `Reviewed`;
}
