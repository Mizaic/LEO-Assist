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
    // Multi-slot (DI-F5E030ED): the dialog now uses the orchestrator
    // helper instead of the single-slot helper. We mock both in
    // case other call-sites in the dialog still reach for the
    // single-slot path (e.g. the per-chip remove flow uses the
    // detach helper directly).
    attachEncounterDayToMultipleMilestones: jest.fn(),
    detachEncounterDayFromMilestone: jest.fn(),
  };
});

const attachMock =
  api.attachEncounterDayToMultipleMilestones as jest.MockedFunction<
    typeof api.attachEncounterDayToMultipleMilestones
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
  benign_interval_days: null,
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
      // VT-900E2453: the picker default is now first_presentation
      // (legacy "presentation" was removed). The conflict-warning
      // path is exercised when the dialog's default slot collides
      // with this existing milestone.
      milestone_type: "first_presentation",
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
      existingLinks={[]}
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

async function pickEpisode(user: ReturnType<typeof userEvent.setup>) {
  // The episode pull-down opens blank (DI-74AF7AD8) so the curator
  // cannot accidentally attach to whichever pathway happened to be
  // open in the drawer. Every test that proceeds past the picker
  // must pick a pathway first. The fixtures only ever have one real
  // episode option, so we pick the first enabled one.
  const select = within(
    screen.getByTestId("milestone-dialog-episode")
  ).getByRole("combobox");
  await user.click(select);
  const options = await screen.findAllByRole("option");
  const real = options.find(
    (o) => o.getAttribute("aria-disabled") !== "true"
  );
  if (!real) throw new Error("No enabled episode option to pick");
  await user.click(real);
}

async function pickPathwaySlot(
  user: ReturnType<typeof userEvent.setup>,
  slot: string
) {
  const select = within(
    screen.getByTestId("milestone-dialog-slot")
  ).getByRole("combobox");
  await user.click(select);
  await user.click(
    screen.getByTestId(`milestone-dialog-slot-option-${slot}`)
  );
  await user.keyboard("{Escape}");
}

describe("MilestoneCurationDialog conflict + replace flow - VT-DEF041C5", () => {
  it("opens with no slot pre-selected and Continue is disabled until the curator picks one (DI-74AF7AD8)", async () => {
    renderDialog();
    expect(screen.queryByTestId("milestone-dialog-slot-chip-first_presentation")).not.toBeInTheDocument();
    expect(screen.getByTestId("milestone-dialog-next")).toBeDisabled();
  });

  it("opens with no episode pre-selected and Continue stays disabled until a pathway is picked (DI-74AF7AD8)", async () => {
    const user = userEvent.setup();
    renderDialog();
    // Episode input renders the placeholder, not the seeded ep-1.
    const episode = screen.getByTestId("milestone-dialog-episode");
    expect(within(episode).getByRole("combobox")).toHaveTextContent(
      /Choose a pathway/i
    );
    // No episode + no slot: Continue is disabled.
    expect(screen.getByTestId("milestone-dialog-next")).toBeDisabled();
    // Picking the pathway alone is not enough -- Continue stays
    // disabled while no slot is picked.
    await pickEpisode(user);
    expect(screen.getByTestId("milestone-dialog-next")).toBeDisabled();
    // Picking a slot as well flips Continue on (the trigger
    // encounter is already pre-selected).
    await pickPathwaySlot(user, "referral");
    await waitFor(() =>
      expect(screen.getByTestId("milestone-dialog-next")).toBeEnabled()
    );
  });

  it("warns when the chosen slot is already filled on a different day", async () => {
    const user = userEvent.setup();
    renderDialog();
    expect(screen.getByTestId("milestone-dialog-day")).toHaveTextContent(
      "(1 of 2 encounters on this day selected)"
    );
    // No slot or episode is pre-picked any more (DI-74AF7AD8). Pick
    // first_presentation, which is already filled on 2025-08-01 by
    // enc-existing, to exercise the conflict path.
    await pickEpisode(user);
    await pickPathwaySlot(user, "first_presentation");
    await user.click(screen.getByTestId("milestone-dialog-next"));
    const conflict = await screen.findByTestId("milestone-dialog-conflict");
    expect(conflict).toHaveTextContent("First presentation");
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

  it("only the trigger encounter is pre-selected; Continue is disabled when nothing is selected", async () => {
    const user = userEvent.setup();
    renderDialog();
    // Pick episode + slot so the encounter-selection assertions are
    // not shadowed by the no-episode / no-slot Continue gates
    // (DI-74AF7AD8).
    await pickEpisode(user);
    await pickPathwaySlot(user, "referral");
    // Trigger encounter is checked, the second one is not.
    const cb1 = screen.getByTestId(
      "milestone-dialog-day-encounter-enc-new-1"
    ) as HTMLElement;
    const cb2 = screen.getByTestId(
      "milestone-dialog-day-encounter-enc-new-2"
    ) as HTMLElement;
    expect(cb1.querySelector("input")?.checked).toBe(true);
    expect(cb2.querySelector("input")?.checked).toBe(false);
    // Unchecking the trigger empties the set; Continue is then
    // disabled until the curator re-selects something.
    await user.click(cb1);
    expect(screen.getByTestId("milestone-dialog-next")).toBeDisabled();
    await user.click(cb2);
    expect(screen.getByTestId("milestone-dialog-next")).toBeEnabled();
  });

  it("Replace attaches only the encounters the curator selected via the multi-slot helper", async () => {
    detachMock.mockResolvedValue({
      success: true,
      episode_id: "ep-1",
      milestone_type: "",
      date: "",
      attempted: ["enc-existing"],
      succeeded: ["enc-existing"],
      alreadyLinked: [],
      failed: [],
      derived_dates: null,
    });
    attachMock.mockResolvedValue({
      episodeId: "ep-1",
      date: "2025-08-14",
      perSlot: [
        {
          success: true,
          episode_id: "ep-1",
          milestone_type: "first_presentation",
          date: "2025-08-14",
          attempted: ["enc-new-1", "enc-new-2"],
          succeeded: ["enc-new-1", "enc-new-2"],
          alreadyLinked: [],
          failed: [],
          derived_dates: null,
        },
      ],
      newlyLinked: 2,
      alreadyLinked: 0,
      failed: 0,
      allSucceeded: true,
    });
    const user = userEvent.setup();
    const { onChanged } = renderDialog();
    await pickEpisode(user);
    await pickPathwaySlot(user, "first_presentation");
    // Curator opts the second encounter in too.
    await user.click(
      screen.getByTestId("milestone-dialog-day-encounter-enc-new-2")
    );
    await user.click(screen.getByTestId("milestone-dialog-next"));
    await user.click(screen.getByTestId("milestone-dialog-replace"));

    await waitFor(() => {
      expect(detachMock).toHaveBeenCalledTimes(1);
      expect(attachMock).toHaveBeenCalledTimes(1);
    });
    // Detach targets the conflicting encounter for the conflicting
    // slot only (DI-F5E030ED), attach passes the picked slot list.
    expect(detachMock).toHaveBeenCalledWith({
      episodeId: "ep-1",
      encounterIds: ["enc-existing"],
      milestoneType: "first_presentation",
    });
    expect(attachMock).toHaveBeenCalledWith({
      episodeId: "ep-1",
      milestoneTypes: ["first_presentation"],
      date: "2025-08-14",
      encounterIds: ["enc-new-1", "enc-new-2"],
    });
    // Detach happens before attach.
    expect(detachMock.mock.invocationCallOrder[0]).toBeLessThan(
      attachMock.mock.invocationCallOrder[0]
    );

    const result = await screen.findByTestId("milestone-dialog-result");
    expect(within(result).getByText(/2 new link/)).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("Pick a different slot returns to the picker without writing", async () => {
    const user = userEvent.setup();
    renderDialog();
    await pickEpisode(user);
    await pickPathwaySlot(user, "first_presentation");
    await user.click(screen.getByTestId("milestone-dialog-next"));
    await user.click(
      screen.getByTestId("milestone-dialog-pick-different-slot")
    );
    expect(screen.getByTestId("milestone-dialog-slot")).toBeInTheDocument();
    expect(detachMock).not.toHaveBeenCalled();
    expect(attachMock).not.toHaveBeenCalled();
  });
});

// Context-tier (DI-50C7E89C) tags such as primary_care_investigations
// or related_gp_visit may legitimately repeat across many days for
// the same episode. The dialog must surface a soft NOTICE (not a
// Replace conflict) and the Add anyway path must call attach
// without any detach -- otherwise existing curated context tags
// silently disappear, which is the bug "milestones keep undoing
// themselves".
const CONTEXT_EPISODE: MissionEpisode = {
  ...EPISODE,
  episode_id: "ep-ctx",
  milestones: [
    {
      milestone_type: "primary_care_investigations",
      encounter_id: "enc-existing-ctx",
      date: "2025-07-14",
    },
  ],
};

const CONTEXT_TRIGGER = {
  encounter_id: "enc-new-ctx",
  date: "2025-07-16",
  text: "GP review, repeat bloods, weight loss notes",
};

function renderContextDialog() {
  const onClose = jest.fn();
  const onChanged = jest.fn();
  render(
    <MilestoneCurationDialog
      open
      triggerEncounter={CONTEXT_TRIGGER}
      sameDayEncounters={[CONTEXT_TRIGGER]}
      episodes={[CONTEXT_EPISODE]}
      defaultEpisodeId="ep-ctx"
      existingLinks={[]}
      reviewerRole="clinician"
      onClose={onClose}
      onChanged={onChanged}
    />
  );
  return { onClose, onChanged };
}

async function pickContextSlot(user: ReturnType<typeof userEvent.setup>) {
  // The slot picker now opens with no pre-selection (DI-74AF7AD8),
  // so we just pick the context tag we want and close the dropdown.
  // The episode pull-down also opens blank, so we pick it first.
  await pickEpisode(user);
  const select = within(
    screen.getByTestId("milestone-dialog-slot")
  ).getByRole("combobox");
  await user.click(select);
  await user.click(
    screen.getByTestId(
      "milestone-dialog-slot-option-primary_care_investigations"
    )
  );
  await user.keyboard("{Escape}");
}

describe("MilestoneCurationDialog context-tier soft notice flow - DI-50C7E89C", () => {
  it("context tag already on another day raises a notice, not a Replace conflict", async () => {
    const user = userEvent.setup();
    renderContextDialog();
    await pickContextSlot(user);
    await user.click(screen.getByTestId("milestone-dialog-next"));

    const notice = await screen.findByTestId("milestone-dialog-notice");
    expect(notice).toHaveTextContent("Primary care investigations");
    expect(notice.textContent).toMatch(/Jul/);
    expect(notice.textContent ?? "").not.toMatch(/enc-existing-ctx/);
    // No Replace button is offered; Add anyway is.
    expect(
      screen.queryByTestId("milestone-dialog-replace")
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("milestone-dialog-add-anyway")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("milestone-dialog-conflict")
    ).not.toBeInTheDocument();
  });

  it("Add anyway calls attach for the new day and never detaches the existing context day", async () => {
    attachMock.mockResolvedValue({
      episodeId: "ep-ctx",
      date: "2025-07-16",
      perSlot: [
        {
          success: true,
          episode_id: "ep-ctx",
          milestone_type: "primary_care_investigations",
          date: "2025-07-16",
          attempted: ["enc-new-ctx"],
          succeeded: ["enc-new-ctx"],
          alreadyLinked: [],
          failed: [],
          derived_dates: null,
        },
      ],
      newlyLinked: 1,
      alreadyLinked: 0,
      failed: 0,
      allSucceeded: true,
    });
    const user = userEvent.setup();
    const { onChanged } = renderContextDialog();
    await pickContextSlot(user);
    await user.click(screen.getByTestId("milestone-dialog-next"));
    await user.click(screen.getByTestId("milestone-dialog-add-anyway"));

    await waitFor(() => {
      expect(attachMock).toHaveBeenCalledTimes(1);
    });
    // Critically: NO detach call. The existing 14 Jul edge stays.
    expect(detachMock).not.toHaveBeenCalled();
    expect(attachMock).toHaveBeenCalledWith({
      episodeId: "ep-ctx",
      milestoneTypes: ["primary_care_investigations"],
      date: "2025-07-16",
      encounterIds: ["enc-new-ctx"],
    });
    const result = await screen.findByTestId("milestone-dialog-result");
    expect(within(result).getByText(/1 new link/)).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("notice-stage Pick a different slot returns to the picker with no writes", async () => {
    const user = userEvent.setup();
    renderContextDialog();
    await pickContextSlot(user);
    await user.click(screen.getByTestId("milestone-dialog-next"));
    expect(
      screen.getByTestId("milestone-dialog-notice")
    ).toBeInTheDocument();
    await user.click(
      screen.getByTestId("milestone-dialog-pick-different-slot")
    );
    expect(screen.getByTestId("milestone-dialog-slot")).toBeInTheDocument();
    expect(attachMock).not.toHaveBeenCalled();
    expect(detachMock).not.toHaveBeenCalled();
  });
});
