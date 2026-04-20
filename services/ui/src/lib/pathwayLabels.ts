/**
 * Plain English label mappings for Mission Control.
 *
 * Single source of truth: database values MUST NOT appear directly
 * in any rendered UI label. All display text comes from this file.
 *
 * Status keys are pinned to the canonical vocabulary in
 * libs/episodes/status.py (mirrored at lib/episodeStatus.ts) -- never
 * hand-write a status string here, always import the constant.
 *
 * Atlas trace:
 *   DO: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EE78E305")
 */
import {
  STATUS_COMPLETED,
  STATUS_CLOSED_BENIGN,
  STATUS_STALE_NO_DIAGNOSIS,
  STATUS_STALE_POST_SPECIALIST,
  STATUS_CLOSED_RELATED,
  STATUS_IN_PROGRESS,
  STATUS_MERGED,
  STATUS_CLOSED_PHANTOM,
} from "@/lib/episodeStatus";

// -- Episode status labels --

export const EPISODE_STATUS_LABELS: Record<string, string> = {
  [STATUS_COMPLETED]: "Confirmed cancer",
  [STATUS_CLOSED_BENIGN]: "No cancer found",
  [STATUS_STALE_NO_DIAGNOSIS]: "No diagnosis after wait",
  [STATUS_STALE_POST_SPECIALIST]: "Specialist seen, no diagnosis",
  [STATUS_CLOSED_RELATED]: "Duplicate pathway closed",
  [STATUS_IN_PROGRESS]: "Still being investigated",
  [STATUS_MERGED]: "Merged pathway",
  [STATUS_CLOSED_PHANTOM]: "Removed (no evidence)",
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
  { value: STATUS_CLOSED_BENIGN, label: "No cancer found" },
  { value: STATUS_STALE_NO_DIAGNOSIS, label: "No diagnosis after wait" },
  { value: STATUS_STALE_POST_SPECIALIST, label: "Specialist seen, no diagnosis" },
  { value: STATUS_CLOSED_RELATED, label: "Duplicate pathway closed" },
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
    case STATUS_COMPLETED:
      return "success";
    case STATUS_IN_PROGRESS:
      return "warning";
    case STATUS_CLOSED_BENIGN:
    case STATUS_STALE_NO_DIAGNOSIS:
    case STATUS_STALE_POST_SPECIALIST:
    case STATUS_CLOSED_RELATED:
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
