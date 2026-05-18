/**
 * NCDA pathway model + breach assessment for the Stage 9 reviewer UI.
 *
 * National rules (NHS Cancer Waiting Times, England):
 *   - FDS-28: 28 days from urgent referral to cancer found OR ruled out.
 *   - Treatment-31: 31 days from cancer found to first treatment.
 *   - Referral-62: 62 days from urgent referral to first treatment.
 *
 * Per-site typical bands come from the Stage 8 pathway-config endpoint
 * (/api/ncda/pathway-config). When a site has no override the defaults in
 * libs/domains/ncda_pathway_config.py apply.
 */

import { daysBetween } from "@/lib/pathwayRisk";

export type NcdaCohort = "1a" | "1b" | "2" | "3" | "4";
export type NcdaTier = "auto" | "suggest" | "review";
export type NcdaBand = "green" | "amber" | "red" | "unknown";

export interface NcdaAnchor {
  encounter_id: string;
  date: string;
  citation_snippet?: string | null;
  top_features?: Array<{ name: string; weight: number }>;
}

export interface NcdaPathway {
  patient_id: string;
  cohort: NcdaCohort;
  tier: NcdaTier;
  site_key?: string | null;
  ftr?: NcdaAnchor | null;
  seen?: NcdaAnchor | null;
  dx?: (NcdaAnchor & { outcome: "cancer_found" | "cancer_excluded" }) | null;
  treatment?: NcdaAnchor | null;
  seen_missing?: boolean;
  treatment_missing?: boolean;
  linkage_probability?: number;
  sub_state?: string | null;
}

export interface PathwayBands {
  site_key: string;
  ftr_to_seen_typical_max_days: number;
  seen_to_dx_typical_max_days: number;
  dx_to_treatment_typical_max_days: number;
  ftr_to_dx_typical_max_days: number;
  ftr_to_treatment_typical_max_days: number;
}

// National breach thresholds.
export const NATIONAL_FDS_28 = 28;
export const NATIONAL_TREATMENT_31 = 31;
export const NATIONAL_REFERRAL_62 = 62;

export interface IntervalAssessment {
  intervalKey: "ftr_to_seen" | "seen_to_dx" | "ftr_to_dx" | "dx_to_treatment" | "ftr_to_treatment";
  startDate?: string | null;
  endDate?: string | null;
  days: number | null;
  band: NcdaBand;
  typicalMaxDays?: number;
  nationalBreachDays?: number;
  breached: boolean;
}

function bandFor(
  days: number | null,
  typicalMax: number | undefined,
  nationalBreach: number | undefined,
): NcdaBand {
  if (days === null) return "unknown";
  if (typicalMax !== undefined && days <= typicalMax) return "green";
  if (nationalBreach !== undefined && days <= nationalBreach) return "amber";
  return "red";
}

export function assessInterval(
  startDate: string | null | undefined,
  endDate: string | null | undefined,
  typicalMax?: number,
  nationalBreach?: number,
): { days: number | null; band: NcdaBand; breached: boolean } {
  if (!startDate || !endDate) {
    return { days: null, band: "unknown", breached: false };
  }
  const days = daysBetween(startDate, endDate);
  const band = bandFor(days, typicalMax, nationalBreach);
  const breached = nationalBreach !== undefined && days > nationalBreach;
  return { days, band, breached };
}

export function assessPathway(
  pathway: NcdaPathway,
  bands: PathwayBands | null,
): IntervalAssessment[] {
  const out: IntervalAssessment[] = [];

  out.push(_interval(
    "ftr_to_seen",
    pathway.ftr?.date,
    pathway.seen?.date,
    bands?.ftr_to_seen_typical_max_days,
    NATIONAL_FDS_28,
  ));
  out.push(_interval(
    "seen_to_dx",
    pathway.seen?.date,
    pathway.dx?.date,
    bands?.seen_to_dx_typical_max_days,
    NATIONAL_FDS_28,
  ));
  out.push(_interval(
    "ftr_to_dx",
    pathway.ftr?.date,
    pathway.dx?.date,
    bands?.ftr_to_dx_typical_max_days,
    NATIONAL_FDS_28,
  ));

  // Treatment intervals only meaningful for cancer_found.
  if (pathway.dx?.outcome === "cancer_found") {
    out.push(_interval(
      "dx_to_treatment",
      pathway.dx?.date,
      pathway.treatment?.date,
      bands?.dx_to_treatment_typical_max_days,
      NATIONAL_TREATMENT_31,
    ));
    out.push(_interval(
      "ftr_to_treatment",
      pathway.ftr?.date,
      pathway.treatment?.date,
      bands?.ftr_to_treatment_typical_max_days,
      NATIONAL_REFERRAL_62,
    ));
  }
  return out;
}

function _interval(
  key: IntervalAssessment["intervalKey"],
  start: string | null | undefined,
  end: string | null | undefined,
  typicalMax: number | undefined,
  nationalBreach: number | undefined,
): IntervalAssessment {
  const a = assessInterval(start, end, typicalMax, nationalBreach);
  return {
    intervalKey: key,
    startDate: start ?? null,
    endDate: end ?? null,
    days: a.days,
    band: a.band,
    typicalMaxDays: typicalMax,
    nationalBreachDays: nationalBreach,
    breached: a.breached,
  };
}
