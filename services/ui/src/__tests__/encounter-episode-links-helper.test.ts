// VT-9C2D6F88 - buildEncounterEpisodeLinks per-encounter rollup
// (DI-5159A336).
//
// Pins the helper that powers the EncounterCard's per-episode chip
// row: every episode the encounter is linked to gets one entry; the
// entry rolls up every milestone slot the encounter fills on that
// episode so the chip's confirm body can say "2 milestone slots
// (First presentation, Referral)".

import {
  buildEncounterEpisodeLinks,
  episodeChipLabel,
} from "../components/mission-control/useMilestoneCuration";
import type { MissionEpisode } from "@/lib/missionControlApi";

function ep(overrides: Partial<MissionEpisode> = {}): MissionEpisode {
  return {
    episode_id: overrides.episode_id ?? "ep",
    cancer_type: overrides.cancer_type ?? null,
    condition_type: overrides.condition_type ?? null,
    status: overrides.status ?? "active",
    cancer_stage: null,
    referral_date: overrides.referral_date ?? null,
    end_date: null,
    diagnostic_interval_days: null,
    benign_interval_days: null,
    primary_care_interval_days: null,
    inferred_outcome: null,
    auto_close_reason: null,
    reviewed_by: null,
    reviewed_at: null,
    audit_notes: null,
    audit_flag: false,
    linked_encounter_ids: overrides.linked_encounter_ids ?? [],
    milestones: overrides.milestones ?? [],
  };
}

describe("buildEncounterEpisodeLinks - VT-9C2D6F88", () => {
  it("returns one entry per episode the encounter is linked to", () => {
    const episodes = [
      ep({
        episode_id: "ep-lung",
        cancer_type: "lung",
        referral_date: "2025-07-14",
        milestones: [
          {
            milestone_type: "first_presentation",
            encounter_id: "enc-1",
            date: "2025-07-14",
          },
        ],
      }),
      ep({
        episode_id: "ep-bowel",
        cancer_type: "bowel",
        referral_date: "2025-04-02",
        milestones: [
          {
            milestone_type: "primary_care_investigations",
            encounter_id: "enc-1",
            date: "2025-04-02",
          },
        ],
      }),
    ];
    const links = buildEncounterEpisodeLinks(episodes).get("enc-1") ?? [];
    expect(links).toHaveLength(2);
    expect(links.map((l) => l.episodeId).sort()).toEqual([
      "ep-bowel",
      "ep-lung",
    ]);
  });

  it("rolls multiple slots on the same episode into one entry", () => {
    const episodes = [
      ep({
        episode_id: "ep-1",
        cancer_type: "lung",
        referral_date: "2025-07-14",
        milestones: [
          {
            milestone_type: "first_presentation",
            encounter_id: "enc-1",
            date: "2025-07-14",
          },
          {
            milestone_type: "referral",
            encounter_id: "enc-1",
            date: "2025-07-14",
          },
        ],
      }),
    ];
    const links = buildEncounterEpisodeLinks(episodes).get("enc-1") ?? [];
    expect(links).toHaveLength(1);
    expect(links[0].milestoneTypes.sort()).toEqual([
      "first_presentation",
      "referral",
    ]);
  });

  it("ignores stale linked_encounter_ids when no real :IS_PART_OF edge is present (DI-5159A336)", () => {
    // Regression: linked_encounter_ids is a denormalised projection
    // from the same MATCH that fills milestones. If milestones is
    // empty, there is no :IS_PART_OF edge and we MUST NOT render a
    // chip -- otherwise clicking unlink hits a 404 ("No IS_PART_OF
    // edge between encounter and episode") and crashes the runtime
    // overlay. The chip lookup is therefore strict: real edges only.
    const episodes = [
      ep({
        episode_id: "ep-1",
        linked_encounter_ids: ["enc-1"],
        milestones: [],
      }),
    ];
    const map = buildEncounterEpisodeLinks(episodes);
    expect(map.has("enc-1")).toBe(false);
    expect(map.get("enc-1") ?? []).toEqual([]);
  });

  it("episodeChipLabel uses the cancer type and short referral day", () => {
    expect(
      episodeChipLabel({
        cancer_type: "lung",
        condition_type: null,
        status: "active",
        referral_date: "2025-07-14",
      })
    ).toBe("lung pathway, ref 14 Jul 25");
  });

  it("episodeChipLabel falls back to a status hint when no cancer type", () => {
    expect(
      episodeChipLabel({
        cancer_type: null,
        condition_type: null,
        status: "in_review",
        referral_date: null,
      })
    ).toBe("Pathway in review");
  });
});
