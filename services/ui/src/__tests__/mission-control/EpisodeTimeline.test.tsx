/**
 * VT-LEO-AI-092 TC-004: EpisodeTimeline renders milestones correctly.
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
  primary_care_interval_days: 14,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  audit_notes: null,
  audit_flag: false,
  milestones: [
    { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
    { milestone_type: "gp_referral", encounter_id: "e-2", date: "2024-06-15" },
    { milestone_type: "cancer_diagnosis", encounter_id: "e-3", date: "2024-07-20" },
  ],
};

describe("EpisodeTimeline", () => {
  test("renders without crashing with a valid completed episode", () => {
    const { container } = render(<EpisodeTimeline episode={BASE_EPISODE} />);
    expect(container.firstChild).toBeTruthy();
  });

  test("renders milestone labels for present milestones", () => {
    render(<EpisodeTimeline episode={BASE_EPISODE} />);
    expect(screen.getByText("First seen")).toBeInTheDocument();
    expect(screen.getByText("Referred")).toBeInTheDocument();
    expect(screen.getByText("Diagnosed")).toBeInTheDocument();
  });

  test("missing milestones render as part of the timeline (no crash)", () => {
    const episodeNoSpecialist = {
      ...BASE_EPISODE,
      milestones: BASE_EPISODE.milestones!.filter(
        (m) => m.milestone_type !== "specialist_visit"
      ),
    };
    const { container } = render(<EpisodeTimeline episode={episodeNoSpecialist} />);
    expect(container.firstChild).toBeTruthy();
    expect(screen.getByText("Specialist")).toBeInTheDocument();
  });

  test("closure episode renders 'Closed' label instead of 'Diagnosed'", () => {
    const closureEpisode: MissionEpisode = {
      ...BASE_EPISODE,
      status: "closed_benign",
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-06-01" },
        { milestone_type: "gp_referral", encounter_id: "e-2", date: "2024-06-15" },
        { milestone_type: "benign_closure", encounter_id: "e-3", date: "2024-07-10" },
      ],
    };
    render(<EpisodeTimeline episode={closureEpisode} />);
    expect(screen.getByText("Closed")).toBeInTheDocument();
    expect(screen.queryByText("Diagnosed")).not.toBeInTheDocument();
  });

  test("compact mode renders without label text", () => {
    const { queryByText } = render(<EpisodeTimeline episode={BASE_EPISODE} compact />);
    expect(queryByText("First seen")).not.toBeInTheDocument();
  });
});
