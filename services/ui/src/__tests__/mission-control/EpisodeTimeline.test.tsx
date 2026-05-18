/**
 * VT-LEO-AI-092 TC-004: EpisodeTimeline renders milestones correctly.
 *
 * The rail uses the canonical post-2026-04 vocabulary
 * (first_presentation, referral, first_seen, outcome_letter,
 * diagnosis_confirmed, benign_closure). Legacy keys
 * (gp_referral, specialist_visit, specialist_outcome_letter,
 * cancer_diagnosis) MUST still light up the matching node so
 * pre-canonical episodes do not regress.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import EpisodeTimeline from "@/components/mission-control/EpisodeTimeline";
import type { MissionEpisode } from "@/lib/missionControlApi";

const BASE_EPISODE: MissionEpisode = {
  episode_id: "ep-001",
  cancer_type: "colorectal",
  condition_type: "cancer",
  status: "completed",
  cancer_stage: "II",
  referral_date: "2024-06-15",
  end_date: "2024-07-20",
  diagnostic_interval_days: 35,
  benign_interval_days: null,
  primary_care_interval_days: 14,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  audit_notes: null,
  audit_flag: false,
  milestones: [
    { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
    { milestone_type: "referral", encounter_id: "e-2", date: "2024-06-15" },
    { milestone_type: "first_seen", encounter_id: "e-3", date: "2024-07-02" },
    { milestone_type: "outcome_letter", encounter_id: "e-4", date: "2024-07-15" },
    { milestone_type: "diagnosis_confirmed", encounter_id: "e-5", date: "2024-07-20" },
  ],
};

describe("EpisodeTimeline", () => {
  test("renders without crashing with a valid completed episode", () => {
    const { container } = render(<EpisodeTimeline episode={BASE_EPISODE} />);
    expect(container.firstChild).toBeTruthy();
  });

  test("renders all five rail labels for a fully populated episode", () => {
    render(<EpisodeTimeline episode={BASE_EPISODE} />);
    expect(screen.getByText("First seen")).toBeInTheDocument();
    expect(screen.getByText("Referred")).toBeInTheDocument();
    expect(screen.getByText("Specialist")).toBeInTheDocument();
    expect(screen.getByText("Outcome letter")).toBeInTheDocument();
    expect(screen.getByText("Diagnosed")).toBeInTheDocument();
  });

  test("renders the Specialist node with the date from the canonical first_seen slot", () => {
    render(<EpisodeTimeline episode={BASE_EPISODE} />);
    // 2024-07-02 -> "02 Jul 24" via en-GB short date
    expect(screen.getByText("02 Jul 24")).toBeInTheDocument();
  });

  test("missing milestones still render with the rail label (greyed out node)", () => {
    const noSpecialist: MissionEpisode = {
      ...BASE_EPISODE,
      milestones: BASE_EPISODE.milestones!.filter(
        (m) => m.milestone_type !== "first_seen"
      ),
    };
    render(<EpisodeTimeline episode={noSpecialist} />);
    expect(screen.getByText("Specialist")).toBeInTheDocument();
  });

  test("closure episode renders 'Closed' label instead of 'Diagnosed'", () => {
    const closure: MissionEpisode = {
      ...BASE_EPISODE,
      status: "closed_benign",
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
        { milestone_type: "referral", encounter_id: "e-2", date: "2024-06-15" },
        { milestone_type: "benign_closure", encounter_id: "e-3", date: "2024-07-10" },
      ],
    };
    render(<EpisodeTimeline episode={closure} />);
    expect(screen.getByText("Closed")).toBeInTheDocument();
    expect(screen.queryByText("Diagnosed")).not.toBeInTheDocument();
  });

  test("legacy slot keys still light up their canonical rail node (DI-6EA84931)", () => {
    // Pre-2026 episodes used gp_referral / specialist_visit /
    // specialist_outcome_letter / cancer_diagnosis. The rail must
    // still date-stamp the right node so historical drawers do not
    // regress to a blank rail after the canonical-vocabulary
    // migration.
    const legacy: MissionEpisode = {
      ...BASE_EPISODE,
      status: "completed",
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
        { milestone_type: "gp_referral", encounter_id: "e-2", date: "2024-06-15" },
        { milestone_type: "specialist_visit", encounter_id: "e-3", date: "2024-07-02" },
        { milestone_type: "specialist_outcome_letter", encounter_id: "e-4", date: "2024-07-15" },
        { milestone_type: "cancer_diagnosis", encounter_id: "e-5", date: "2024-07-20" },
      ],
    };
    render(<EpisodeTimeline episode={legacy} />);
    expect(screen.getByText("First seen")).toBeInTheDocument();
    expect(screen.getByText("Referred")).toBeInTheDocument();
    expect(screen.getByText("Specialist")).toBeInTheDocument();
    expect(screen.getByText("Outcome letter")).toBeInTheDocument();
    expect(screen.getByText("Diagnosed")).toBeInTheDocument();
    // The Specialist node must show the legacy date (02 Jul 24) so
    // it is clear the alias resolved.
    expect(screen.getByText("02 Jul 24")).toBeInTheDocument();
  });

  test("manual curation: a freshly-attached diagnosis_confirmed milestone shows on the rail (DI-6EA84931)", () => {
    // Regression for the rail-vocabulary mismatch: prior to the
    // canonical-vocabulary fix the rail looked up "cancer_diagnosis"
    // but the curator wrote "diagnosis_confirmed", so manually set
    // milestones never appeared.
    const manual: MissionEpisode = {
      ...BASE_EPISODE,
      status: "completed",
      end_date: null, // forces the rail to read the slot map directly
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
        { milestone_type: "referral", encounter_id: "e-2", date: "2024-06-15" },
        { milestone_type: "diagnosis_confirmed", encounter_id: "e-3", date: "2024-07-20" },
      ],
    };
    render(<EpisodeTimeline episode={manual} />);
    expect(screen.getByText("Diagnosed")).toBeInTheDocument();
    expect(screen.getByText("20 Jul 24")).toBeInTheDocument();
  });

  test("benign_closure slot shows on the rail even when status is still in_review (DI-3A19BE12)", () => {
    // Regression for the user-reported bug "we need to show where the
    // benign closure": before this fix the rail hid the Closed node
    // unless episode.status was already in CLOSURE_REASON_STATUSES,
    // which meant a manually attached benign_closure did not show
    // until the next pipeline rebuild bumped the status.
    const stillInReview: MissionEpisode = {
      ...BASE_EPISODE,
      status: "review",
      end_date: null,
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
        { milestone_type: "referral", encounter_id: "e-2", date: "2024-06-15" },
        { milestone_type: "benign_closure", encounter_id: "e-3", date: "2024-07-10" },
      ],
    };
    render(<EpisodeTimeline episode={stillInReview} />);
    expect(screen.getByText("Closed")).toBeInTheDocument();
    expect(screen.getByText("10 Jul 24")).toBeInTheDocument();
    // No Diagnosed node when only the closure slot is attached.
    expect(screen.queryByText("Diagnosed")).not.toBeInTheDocument();
  });

  test("rail shows both Diagnosed and Closed when both slots are attached", () => {
    // A rare but real case: a closure slot was attached after a
    // diagnosis_confirmed slot (e.g. confirmed cancer, then later
    // re-classified as benign closure). The clinician needs to see
    // both events on the rail.
    const both: MissionEpisode = {
      ...BASE_EPISODE,
      status: "review",
      end_date: null,
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
        { milestone_type: "referral", encounter_id: "e-2", date: "2024-06-15" },
        { milestone_type: "diagnosis_confirmed", encounter_id: "e-3", date: "2024-07-20" },
        { milestone_type: "benign_closure", encounter_id: "e-4", date: "2024-08-05" },
      ],
    };
    render(<EpisodeTimeline episode={both} />);
    expect(screen.getByText("Diagnosed")).toBeInTheDocument();
    expect(screen.getByText("Closed")).toBeInTheDocument();
  });

  test("rail still falls back to status-based default when no terminal slot is attached", () => {
    // When neither benign_closure nor diagnosis_confirmed has data,
    // the rail must still show the right "we're waiting for X"
    // placeholder driven by episode.status (so an in-progress active
    // pathway shows the empty Diagnosed node, and a closed_benign
    // pathway shows the empty Closed node).
    const empty: MissionEpisode = {
      ...BASE_EPISODE,
      status: "active",
      end_date: null,
      milestones: [
        { milestone_type: "referral", encounter_id: "e-1", date: "2024-06-15" },
      ],
    };
    render(<EpisodeTimeline episode={empty} />);
    expect(screen.getByText("Diagnosed")).toBeInTheDocument();
    expect(screen.queryByText("Closed")).not.toBeInTheDocument();

    // And a closed pathway with no slot data still gets the
    // placeholder Closed node.
    const closedNoSlot: MissionEpisode = {
      ...BASE_EPISODE,
      status: "closed_benign",
      end_date: null,
      milestones: [
        { milestone_type: "referral", encounter_id: "e-1", date: "2024-06-15" },
      ],
    };
    const { unmount } = render(<EpisodeTimeline episode={empty} />);
    unmount();
    render(<EpisodeTimeline episode={closedNoSlot} />);
    expect(screen.getByText("Closed")).toBeInTheDocument();
  });

  test("compact mode renders without label text", () => {
    const { queryByText } = render(<EpisodeTimeline episode={BASE_EPISODE} compact />);
    expect(queryByText("First seen")).not.toBeInTheDocument();
  });

  // -- Pathway interval overlay bands --
  // The rail carries two coloured ribbons below the nodes that show
  // the two NHS pathway intervals at a glance: primary care
  // (first_presentation -> referral) and diagnostic (referral ->
  // terminal). Tests below pin the days arithmetic, the colour
  // banding, the terminal-node selection (closure beats diagnosis)
  // and the safe degradation when slots are missing.

  test("renders both interval bands with day counts when first_pres + referral + diagnosis are present", () => {
    render(<EpisodeTimeline episode={BASE_EPISODE} />);
    const primary = screen.getByTestId("interval-band-primary-care");
    const diagnostic = screen.getByTestId("interval-band-diagnostic");
    // 2024-06-01 -> 2024-06-15 = 14d
    expect(primary).toHaveTextContent("Primary care: 14d");
    // 2024-06-15 -> 2024-07-20 = 35d
    expect(diagnostic).toHaveTextContent("Referral to diagnosed: 35d");
  });

  test("diagnostic band uses 'closed' label when benign_closure is the terminal node", () => {
    const closure: MissionEpisode = {
      ...BASE_EPISODE,
      status: "closed_benign",
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
        { milestone_type: "referral", encounter_id: "e-2", date: "2024-06-15" },
        { milestone_type: "benign_closure", encounter_id: "e-3", date: "2024-07-10" },
      ],
    };
    render(<EpisodeTimeline episode={closure} />);
    const diagnostic = screen.getByTestId("interval-band-diagnostic");
    // 2024-06-15 -> 2024-07-10 = 25d, terminal label = "closed"
    expect(diagnostic).toHaveTextContent("Referral to closed: 25d");
  });

  test("when both diagnosis and closure are attached, closure wins as terminal (rail-end)", () => {
    const both: MissionEpisode = {
      ...BASE_EPISODE,
      status: "review",
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
        { milestone_type: "referral", encounter_id: "e-2", date: "2024-06-15" },
        { milestone_type: "diagnosis_confirmed", encounter_id: "e-3", date: "2024-07-20" },
        { milestone_type: "benign_closure", encounter_id: "e-4", date: "2024-08-05" },
      ],
    };
    render(<EpisodeTimeline episode={both} />);
    // Closure is the actual pathway end so the diagnostic band runs
    // referral -> closure (51d), not referral -> diagnosis (35d).
    expect(screen.getByTestId("interval-band-diagnostic")).toHaveTextContent(
      "Referral to closed: 51d"
    );
  });

  test("primary care band is hidden when first_presentation has no date", () => {
    const noFirstPres: MissionEpisode = {
      ...BASE_EPISODE,
      milestones: BASE_EPISODE.milestones!.filter(
        (m) => m.milestone_type !== "first_presentation"
      ),
    };
    render(<EpisodeTimeline episode={noFirstPres} />);
    expect(screen.queryByTestId("interval-band-primary-care")).not.toBeInTheDocument();
    // Diagnostic band still renders because referral + diagnosis are present.
    expect(screen.getByTestId("interval-band-diagnostic")).toBeInTheDocument();
  });

  test("diagnostic band is hidden when referral has no date", () => {
    // The rail falls back to episode.referral_date when there's no
    // explicit referral milestone row, so to truly hide the referral
    // node both the row AND the fallback must be cleared.
    const noReferral: MissionEpisode = {
      ...BASE_EPISODE,
      referral_date: null,
      milestones: BASE_EPISODE.milestones!.filter(
        (m) => m.milestone_type !== "referral"
      ),
    };
    render(<EpisodeTimeline episode={noReferral} />);
    expect(screen.queryByTestId("interval-band-diagnostic")).not.toBeInTheDocument();
    expect(screen.queryByTestId("interval-band-primary-care")).not.toBeInTheDocument();
  });

  test("compact mode hides the interval overlay row", () => {
    render(<EpisodeTimeline episode={BASE_EPISODE} compact />);
    expect(screen.queryByTestId("pathway-interval-overlays")).not.toBeInTheDocument();
    expect(screen.queryByTestId("interval-band-primary-care")).not.toBeInTheDocument();
    expect(screen.queryByTestId("interval-band-diagnostic")).not.toBeInTheDocument();
  });

  test("interval bands degrade gracefully when neither diagnosis nor closure is attached", () => {
    const inFlight: MissionEpisode = {
      ...BASE_EPISODE,
      status: "active",
      end_date: null,
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
        { milestone_type: "referral", encounter_id: "e-2", date: "2024-06-15" },
      ],
    };
    render(<EpisodeTimeline episode={inFlight} />);
    // Primary care band still renders (we have the two endpoints).
    expect(screen.getByTestId("interval-band-primary-care")).toHaveTextContent(
      "Primary care: 14d"
    );
    // Diagnostic band hides because there's no terminal date yet.
    expect(screen.queryByTestId("interval-band-diagnostic")).not.toBeInTheDocument();
  });
});
