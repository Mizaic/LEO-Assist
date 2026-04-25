// VT-9C2D6F88 -- useEncounterEpisodeChips idempotency (DI-5159A336).
//
// Pins the hook contract that powers the per-episode chip unlink
// flow on EncounterCard. The chip lookup must be derived from real
// :IS_PART_OF edges (milestones array), and unlink must be
// idempotent: a 404 from the backend ("No IS_PART_OF edge between
// encounter and episode") means the desired post-condition is
// already true (no edge), so the hook treats it as success and
// still calls onChanged so the stale chip disappears.

import "@testing-library/jest-dom";
import { renderHook, act } from "@testing-library/react";

import { useEncounterEpisodeChips } from "@/components/mission-control/useMilestoneCuration";
import type { MissionEpisode } from "@/lib/missionControlApi";

const detachMock = jest.fn();
jest.mock("@/lib/missionControlApi", () => {
  const actual = jest.requireActual("@/lib/missionControlApi");
  return {
    ...actual,
    detachEncounterFromEpisode: (...args: unknown[]) => detachMock(...args),
  };
});

function ep(overrides: Partial<MissionEpisode> = {}): MissionEpisode {
  return {
    episode_id: overrides.episode_id ?? "ep-1",
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

beforeEach(() => {
  detachMock.mockReset();
});

describe("useEncounterEpisodeChips - VT-9C2D6F88", () => {
  it("treats a 'No IS_PART_OF edge' 404 as success and still refreshes (DI-5159A336)", async () => {
    detachMock.mockRejectedValueOnce(
      new Error("No IS_PART_OF edge between encounter and episode")
    );
    const onChanged = jest.fn().mockResolvedValue(undefined);
    const episodes: MissionEpisode[] = [
      ep({
        episode_id: "ep-1",
        milestones: [
          {
            milestone_type: "first_presentation",
            encounter_id: "enc-1",
            date: "2025-07-14",
          },
        ],
      }),
    ];
    const { result } = renderHook(() =>
      useEncounterEpisodeChips(episodes, onChanged)
    );

    await act(async () => {
      await result.current.unlink("enc-1", "ep-1");
    });

    expect(detachMock).toHaveBeenCalledWith("ep-1", "enc-1");
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("rethrows a non-404 server error so the chip surfaces it", async () => {
    detachMock.mockRejectedValueOnce(new Error("Pathway is locked for review"));
    const onChanged = jest.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      useEncounterEpisodeChips([], onChanged)
    );

    await expect(
      act(async () => {
        await result.current.unlink("enc-1", "ep-1");
      })
    ).rejects.toThrow("Pathway is locked for review");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("calls detach then onChanged on a successful unlink", async () => {
    detachMock.mockResolvedValueOnce({ success: true });
    const onChanged = jest.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      useEncounterEpisodeChips([], onChanged)
    );

    await act(async () => {
      await result.current.unlink("enc-1", "ep-1");
    });

    expect(detachMock).toHaveBeenCalledTimes(1);
    expect(onChanged).toHaveBeenCalledTimes(1);
  });
});
