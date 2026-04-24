/**
 * Shared milestone slot vocabulary.
 *
 * Two tiers (group field):
 *
 *   1. "pathway" -- the canonical nine the AI engine can emit:
 *      - eight from services/analysis_worker/app/episode_engine/
 *        schemas.py Milestone.type Literal (first_presentation,
 *        referral, first_seen, outcome_letter, diagnosis_confirmed,
 *        treatment_started, treatment_completed, benign_closure)
 *      - care_obstruction from services/analysis_worker/app/
 *        analyzers/anchor_detector.py
 *      These drive episode date roll-ups (referral_date / start_date
 *      / end_date) -- see _episode_crud_helpers.py.
 *
 *   2. "context" -- supporting evidence the curator can attach but
 *      the AI engine does NOT emit. They never feed the date roll-ups
 *      and exist only so the timeline carries the full reviewer
 *      narrative (repeat GP visits, primary-care investigations,
 *      referral admin, repeat specialist visits, specialist
 *      diagnostics, related correspondence). DI-50C7E89C.
 *
 * Manual curators can assign any value in either tier; the AI engine
 * will only ever fill the pathway nine, which protects cancer-pathway
 * KPI roll-ups.
 *
 * Legacy values (presentation, specialist_visit, first_clinic_visit,
 * clinic_visit, first_clinic, investigation, diagnosis,
 * treatment_decision, treatment, first_treatment, related) still
 * exist on historical :IS_PART_OF edges and render via the
 * milestoneLabel() underscore-replace fallback below, but they are
 * no longer offered in the picker.
 *
 * The backend write-side allow-list is mirrored in
 * services/analytics_api/app/routers/_episode_crud_helpers.py
 * (MILESTONE_TYPES); both must move together. Pinned by VT-900E2453.
 *
 * Atlas trace:
 *   DO: DO-D7CFC1EF, DO-7986A957
 *   DI: DI-26D4D710, DI-4B99678C, DI-50C7E89C
 *   VT: VT-900E2453
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-D7CFC1EF")
 */

export type MilestoneGroup = "pathway" | "context";

export interface MilestoneOption {
  value: string;
  label: string;
  // "pathway" = AI engine populates this slot AND it feeds episode
  // date roll-ups. "context" = curator-only, descriptive tag only.
  group: MilestoneGroup;
}

// Order matches the cancer-pathway sequence within each tier so the
// grouped picker reads top-to-bottom in clinical order: presentation
// -> referral -> first seen -> outcome -> diagnosis -> treatment
// start -> treatment end -> benign closure -> care obstruction
// (pathway tier), then the supporting-context tier.
export const MILESTONE_OPTIONS: MilestoneOption[] = [
  { value: "first_presentation", label: "First presentation", group: "pathway" },
  { value: "referral", label: "Referral", group: "pathway" },
  { value: "first_seen", label: "First seen by specialist", group: "pathway" },
  { value: "outcome_letter", label: "Specialist outcome letter", group: "pathway" },
  { value: "diagnosis_confirmed", label: "Diagnosis confirmed", group: "pathway" },
  { value: "treatment_started", label: "Treatment started", group: "pathway" },
  { value: "treatment_completed", label: "Treatment completed", group: "pathway" },
  { value: "benign_closure", label: "Closed as benign", group: "pathway" },
  { value: "care_obstruction", label: "Care obstruction", group: "pathway" },
  // Supporting-context tier (DI-50C7E89C). Curator-only tags that
  // colour-in the timeline but never alter date roll-ups.
  { value: "related_gp_visit", label: "Related GP visit", group: "context" },
  {
    value: "primary_care_investigations",
    label: "Primary care investigations",
    group: "context",
  },
  { value: "referral_admin", label: "Referral admin", group: "context" },
  { value: "referral_sent", label: "Referral sent", group: "context" },
  {
    value: "related_specialist_visit",
    label: "Related specialist visit",
    group: "context",
  },
  {
    value: "specialist_diagnostics",
    label: "Specialist diagnostics",
    group: "context",
  },
  {
    value: "related_correspondence",
    label: "Related correspondence",
    group: "context",
  },
];

export const MILESTONE_GROUP_LABEL: Record<MilestoneGroup, string> = {
  pathway: "Pathway events (AI also fills these)",
  context: "Supporting context (AI suggests, curator confirms)",
};

export function milestoneLabel(value: string): string {
  return (
    MILESTONE_OPTIONS.find((opt) => opt.value === value)?.label ??
    value.replaceAll("_", " ")
  );
}

// Tier helpers used by MilestoneCurationDialog to decide whether a
// same-slot-different-day situation is a hard conflict (pathway:
// only-one-per-episode events like first_presentation) or a soft
// notice (context: descriptive tags that legitimately repeat across
// days, like primary_care_investigations or related_gp_visit). An
// unknown legacy value is treated as pathway by default so the
// strict Replace flow still protects historical data. DI-50C7E89C.
export function milestoneTier(value: string): MilestoneGroup {
  return MILESTONE_OPTIONS.find((opt) => opt.value === value)?.group ?? "pathway";
}

export function isContextMilestone(value: string): boolean {
  return milestoneTier(value) === "context";
}
