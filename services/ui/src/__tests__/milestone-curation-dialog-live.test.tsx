// VT-DEF041C5 live-render path -- per-encounter inline milestone curation
//
// Live React-Testing-Library check that MilestoneCurationDialog
// detects a same-slot, different-day conflict, asks the reviewer
// to keep / replace / pick another slot, and on Replace fires the
// detach + attach orchestrators in the right order.

import "@testing-library/jest-dom";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import MilestoneCurationDialog from "@/components/mission-control/MilestoneCurationDialog";
import * as api from "@/lib/missionControlApi";
import type { MissionEpisode } from "@/lib/missionControlApi";

jest.mock("@/lib/missionControlApi", () => {
  const actual = jest.requireActual("@/lib/missionControlApi");
  return {
    __esModule: true,
    ...actual,
    attachEncounterDayToMilestone: jest.fn(),
    detachEncounterDayFromMilestone: jest.fn(),
  };
});

const attachMock = api.attachEncounterDayToMilestone as jest.MockedFunction<
  typeof api.attachEncounterDayToMilestone
>;
const detachMock = api.detachEncounterDayFromMilestone as jest.MockedFunction<
  typeof api.detachEncounterDayFromMilestone
>;

const EPISODE: MissionEpisode = {
  episode_id: "ep-1",
  cancer_type: "lung",
  condition_type: null,
  status: "open",
  cancer_stage: null,
  referral_date: "2025-08-10",
  end_date: null,
  diagnostic_interval_days: null,
  primary_care_interval_days: null,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  audit_notes: null,
  audit_flag: false,
  linked_encounter_ids: ["enc-existing"],
  milestones: [
    {
      milestone_type: "presentation",
      encounter_id: "enc-existing",
      date: "2025-08-01",
    },
  ],
};

const SAME_DAY = [
  {
    encounter_id: "enc-new-1",
    date: "2025-08-14",
    text: "GP visit, cough, weight loss",
  },
  {
    encounter_id: "enc-new-2",
    date: "2025-08-14",
    text: "Lab order: CXR, FBC",
  },
];

function renderDialog() {
  const onClose = jest.fn();
  const onChanged = jest.fn();
  render(
    <MilestoneCurationDialog
      open
      triggerEncounter={SAME_DAY[0]}
      sameDayEncounters={SAME_DAY}
      episodes={[EPISODE]}
      defaultEpisodeId="ep-1"
      existingLink={null}
      reviewerRole="clinician"
      onClose={onClose}
      onChanged={onChanged}
    />
  );
  return { onClose, onChanged };
}

beforeEach(() => {
  attachMock.mockReset();
  detachMock.mockReset();
});

describe("MilestoneCurationDialog conflict + replace flow - VT-DEF041C5", () => {
  it("warns when the chosen slot is already filled on a different day", async () => {
    const user = userEvent.setup();
    renderDialog();
    expect(screen.getByTestId("milestone-dialog-day")).toHaveTextContent(
      "(2 encounters on this day)"
    );
    // The default slot is "presentation", which is already filled
    // on 2025-08-01 by enc-existing.
    await user.click(screen.getByTestId("milestone-dialog-next"));
    const conflict = await screen.findByTestId("milestone-dialog-conflict");
    expect(conflict).toHaveTextContent("Presentation");
    // The conflict alert names the existing date.
    expect(conflict.textContent).toMatch(/Aug/);
    // No raw encounter ID is shown in the conflict body.
    expect(conflict.textContent ?? "").not.toMatch(/enc-existing/);
    // Replace button is offered.
    expect(
      screen.getByTestId("milestone-dialog-replace")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("milestone-dialog-pick-different-slot")
    ).toBeInTheDocument();
  });

  it("Replace detaches the conflicting milestone, then attaches the new same-day group", async () => {
    detachMock.mockResolvedValue({
      success: true,
      episode_id: "ep-1",
      milestone_type: "",
      date: "",
      attempted: ["enc-existing"],
      succeeded: ["enc-existing"],
      failed: [],
      derived_dates: null,
    });
    attachMock.mockResolvedValue({
      success: true,
      episode_id: "ep-1",
      milestone_type: "presentation",
      date: "2025-08-14",
      attempted: ["enc-new-1", "enc-new-2"],
      succeeded: ["enc-new-1", "enc-new-2"],
      failed: [],
      derived_dates: null,
    });
    const user = userEvent.setup();
    const { onChanged } = renderDialog();
    await user.click(screen.getByTestId("milestone-dialog-next"));
    await user.click(screen.getByTestId("milestone-dialog-replace"));

    await waitFor(() => {
      expect(detachMock).toHaveBeenCalledTimes(1);
      expect(attachMock).toHaveBeenCalledTimes(1);
    });
    // Detach targets the conflicting encounter, attach targets the
    // new same-day group with the chosen slot.
    expect(detachMock).toHaveBeenCalledWith({
      episodeId: "ep-1",
      encounterIds: ["enc-existing"],
    });
    expect(attachMock).toHaveBeenCalledWith({
      episodeId: "ep-1",
      milestoneType: "presentation",
      date: "2025-08-14",
      encounterIds: ["enc-new-1", "enc-new-2"],
    });
    // Detach happens before attach.
    expect(detachMock.mock.invocationCallOrder[0]).toBeLessThan(
      attachMock.mock.invocationCallOrder[0]
    );

    const result = await screen.findByTestId("milestone-dialog-result");
    expect(within(result).getByText(/2 encounter/)).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("Pick a different slot returns to the picker without writing", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByTestId("milestone-dialog-next"));
    await user.click(
      screen.getByTestId("milestone-dialog-pick-different-slot")
    );
    expect(screen.getByTestId("milestone-dialog-slot")).toBeInTheDocument();
    expect(detachMock).not.toHaveBeenCalled();
    expect(attachMock).not.toHaveBeenCalled();
  });
});
