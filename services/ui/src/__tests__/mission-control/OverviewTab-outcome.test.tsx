/**
 * Outcome / Outcome date in the OverviewTab header MUST follow the
 * "slot evidence wins" rule: when a benign_closure or
 * diagnosis_confirmed milestone has been attached the header reads
 * those, not episode.status / episode.end_date. This is the same
 * rule the rail already uses (DI-3A19BE12 follow-up).
 *
 * Bug screenshot: an episode whose status was still "active" but
 * which had a diagnosis_confirmed slot dated 18 Sep 25 showed
 * "Outcome: active. -- Outcome date: --" in the header while the
 * rail right below it correctly showed "Diagnosed 18 Sep 25".
 *
 * VT covered: VT-454970DE (Mission Control Frontend UI -- Timeline
 * rendering / Outcome derivation).
 */

import { slotDerivedOutcome } from "@/components/mission-control/OverviewTab";
import type { MissionEpisode } from "@/lib/missionControlApi";

const BASE: MissionEpisode = {
  episode_id: "ep-001",
  cancer_type: "breast",
  condition_type: "cancer",
  status: "active",
  cancer_stage: null,
  referral_date: "2025-08-12",
  end_date: null,
  diagnostic_interval_days: 37,
  benign_interval_days: null,
  primary_care_interval_days: 0,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  audit_notes: null,
  audit_flag: false,
  milestones: [],
};

describe("slotDerivedOutcome", () => {
  test("returns null when no terminal slot is attached (caller falls back to status / end_date)", () => {
    expect(slotDerivedOutcome(BASE)).toBeNull();
  });

  test("returns the diagnosis_confirmed slot date and 'Cancer confirmed in <type>' text when status is still 'active'", () => {
    // This is the exact bug from the screenshot: episode.status is
    // still "active" because the recompute hasn't run yet, but a
    // diagnosis_confirmed slot is on the rail and the header MUST
    // reflect that.
    const ep: MissionEpisode = {
      ...BASE,
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2025-08-12" },
        { milestone_type: "referral", encounter_id: "e-2", date: "2025-08-12" },
        { milestone_type: "diagnosis_confirmed", encounter_id: "e-3", date: "2025-09-18" },
      ],
    };
    expect(slotDerivedOutcome(ep)).toEqual({
      text: "Cancer confirmed in breast.",
      date: "2025-09-18",
    });
  });

  test("includes the cancer stage when present", () => {
    const ep: MissionEpisode = {
      ...BASE,
      cancer_stage: "II",
      milestones: [
        { milestone_type: "diagnosis_confirmed", encounter_id: "e-1", date: "2025-09-18" },
      ],
    };
    const out = slotDerivedOutcome(ep);
    expect(out?.text).toBe("Cancer confirmed in breast (stage II).");
  });

  test("benign_closure slot beats diagnosis_confirmed when both are attached (closure is the actual pathway end)", () => {
    const ep: MissionEpisode = {
      ...BASE,
      milestones: [
        { milestone_type: "diagnosis_confirmed", encounter_id: "e-1", date: "2025-09-18" },
        { milestone_type: "benign_closure", encounter_id: "e-2", date: "2025-10-05" },
      ],
    };
    expect(slotDerivedOutcome(ep)).toEqual({
      text: "No cancer found.",
      date: "2025-10-05",
    });
  });

  test("benign_closure slot returns 'No cancer found.' even when status is still 'in_review'", () => {
    const ep: MissionEpisode = {
      ...BASE,
      status: "in_review",
      milestones: [
        { milestone_type: "benign_closure", encounter_id: "e-1", date: "2025-09-30" },
      ],
    };
    expect(slotDerivedOutcome(ep)).toEqual({
      text: "No cancer found.",
      date: "2025-09-30",
    });
  });

  test("legacy 'cancer_diagnosis' key is honoured (matches EpisodeTimeline LEGACY_ALIASES)", () => {
    // Pre-2026 episodes used the legacy "cancer_diagnosis" slot key.
    // The header derivation MUST treat it as a diagnosis_confirmed
    // for the same reason the rail does -- the alternative is a
    // header that reads "active" for every legacy episode that has
    // a diagnosis on the rail.
    const ep: MissionEpisode = {
      ...BASE,
      milestones: [
        { milestone_type: "cancer_diagnosis", encounter_id: "e-1", date: "2025-09-18" },
      ],
    };
    expect(slotDerivedOutcome(ep)).toEqual({
      text: "Cancer confirmed in breast.",
      date: "2025-09-18",
    });
  });

  test("returns null for an episode that only has non-terminal milestones", () => {
    const ep: MissionEpisode = {
      ...BASE,
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2025-08-12" },
        { milestone_type: "referral", encounter_id: "e-2", date: "2025-08-12" },
        { milestone_type: "first_seen", encounter_id: "e-3", date: "2025-09-11" },
        { milestone_type: "outcome_letter", encounter_id: "e-4", date: "2025-09-18" },
      ],
    };
    expect(slotDerivedOutcome(ep)).toBeNull();
  });

  test("omits the cancer type when the episode has none", () => {
    const ep: MissionEpisode = {
      ...BASE,
      cancer_type: null,
      milestones: [
        { milestone_type: "diagnosis_confirmed", encounter_id: "e-1", date: "2025-09-18" },
      ],
    };
    expect(slotDerivedOutcome(ep)?.text).toBe("Cancer confirmed.");
  });
});
