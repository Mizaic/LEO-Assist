import React from "react";
import { render, screen } from "@testing-library/react";
import EpisodeTimelineView from "../EpisodeTimelineView";
import { assessPathwayRisk, type Episode, type PathwayRisk } from "@/lib/pathwayRisk";

const TODAY = "2026-02-26";

function withRisk(ep: Episode): Episode & { risk: PathwayRisk } {
  return { ...ep, risk: assessPathwayRisk(ep, TODAY) };
}

describe("EpisodeTimelineView", () => {
  it("renders cancer type heading and risk chip", () => {
    const ep = withRisk({
      episode_id: "EP-001",
      condition_type: "Colorectal",
      status: "active",
      referral_date: "2026-02-20",
      milestones: [
        { encounter_id: "E1", date: "2026-02-20", milestone_type: "referral" },
      ],
    });
    render(<EpisodeTimelineView episode={ep} risk={ep.risk} />);
    expect(screen.getByText("Colorectal")).toBeInTheDocument();
  });

  it("renders achieved milestones in the stepper", () => {
    const ep = withRisk({
      episode_id: "EP-002",
      condition_type: "Lung",
      status: "active",
      referral_date: "2026-02-01",
      milestones: [
        { encounter_id: "E1", date: "2026-02-01", milestone_type: "referral" },
        { encounter_id: "E2", date: "2026-02-10", milestone_type: "first_clinic" },
      ],
    });
    render(<EpisodeTimelineView episode={ep} risk={ep.risk} />);
    expect(screen.getByText("Referral")).toBeInTheDocument();
    expect(screen.getByText("First Specialist Clinic")).toBeInTheDocument();
  });

  it("renders pending milestone placeholders", () => {
    const ep = withRisk({
      episode_id: "EP-003",
      condition_type: "Breast",
      status: "active",
      referral_date: "2026-02-20",
      milestones: [
        { encounter_id: "E1", date: "2026-02-20", milestone_type: "referral" },
      ],
    });
    render(<EpisodeTimelineView episode={ep} risk={ep.risk} />);
    expect(screen.getByText(/Diagnosis/)).toBeInTheDocument();
    expect(screen.getByText(/First Treatment/)).toBeInTheDocument();
  });

  it("shows next milestone label for the expected step", () => {
    const ep = withRisk({
      episode_id: "EP-004",
      condition_type: "Skin",
      status: "active",
      referral_date: "2026-02-20",
      milestones: [
        { encounter_id: "E1", date: "2026-02-18", milestone_type: "presentation" },
        { encounter_id: "E2", date: "2026-02-20", milestone_type: "referral" },
      ],
    });
    render(<EpisodeTimelineView episode={ep} risk={ep.risk} />);
    expect(screen.getByText(/First Specialist Clinic \(next\)/)).toBeInTheDocument();
  });

  it("shows breach summary chips when breaches exist", () => {
    const ep = withRisk({
      episode_id: "EP-005",
      condition_type: "Prostate",
      status: "active",
      referral_date: "2026-01-01",
      milestones: [
        { encounter_id: "E1", date: "2026-01-01", milestone_type: "referral" },
      ],
    });
    render(<EpisodeTimelineView episode={ep} risk={ep.risk} />);
    const twwMatches = screen.getAllByText(/2WW/);
    expect(twwMatches.length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/overdue/).length).toBeGreaterThanOrEqual(1);
  });

  it("shows alert when pathway is at risk or breached", () => {
    const ep = withRisk({
      episode_id: "EP-006",
      condition_type: "Breast",
      status: "active",
      referral_date: "2026-02-01",
      milestones: [
        { encounter_id: "E1", date: "2026-02-01", milestone_type: "referral" },
      ],
    });
    render(<EpisodeTimelineView episode={ep} risk={ep.risk} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("renders info chips for pathway, patient, referral date", () => {
    const ep = withRisk({
      episode_id: "EP-007",
      patient_id: "PAT-123",
      condition_type: "Lung",
      status: "active",
      referral_date: "2026-02-15",
      milestones: [],
    });
    render(<EpisodeTimelineView episode={ep} risk={ep.risk} />);
    expect(screen.getByText("EP-007")).toBeInTheDocument();
    expect(screen.getByText("PAT-123")).toBeInTheDocument();
    expect(screen.getByText("2026-02-15")).toBeInTheDocument();
  });

  it("renders pending milestone placeholders when no milestones achieved", () => {
    const ep = withRisk({
      episode_id: "EP-008",
      condition_type: "Unknown",
      status: "active",
      referral_date: undefined,
      milestones: [],
    });
    render(<EpisodeTimelineView episode={ep} risk={ep.risk} />);
    expect(screen.getByText(/Presentation/)).toBeInTheDocument();
    expect(screen.getAllByText(/Referral/).length).toBeGreaterThanOrEqual(1);
  });

  it("shows day-gap chip between consecutive milestones", () => {
    const ep = withRisk({
      episode_id: "EP-009",
      condition_type: "Breast",
      status: "active",
      referral_date: "2026-02-01",
      milestones: [
        { encounter_id: "E1", date: "2026-02-01", milestone_type: "referral" },
        { encounter_id: "E2", date: "2026-02-08", milestone_type: "first_clinic" },
      ],
    });
    render(<EpisodeTimelineView episode={ep} risk={ep.risk} />);
    expect(screen.getByText("7d")).toBeInTheDocument();
  });

  it("renders related pathways section when siblings provided", () => {
    const main = withRisk({
      episode_id: "EP-MAIN",
      patient_id: "PAT-A",
      condition_type: "Lung",
      status: "active",
      referral_date: "2026-02-01",
      milestones: [
        { encounter_id: "E1", date: "2026-02-01", milestone_type: "referral" },
      ],
    });
    const sibling = withRisk({
      episode_id: "EP-SIB",
      patient_id: "PAT-A",
      condition_type: "Breast",
      status: "active",
      referral_date: "2026-02-05",
      milestones: [],
    });

    render(
      <EpisodeTimelineView
        episode={main}
        risk={main.risk}
        siblingEpisodes={[sibling]}
      />,
    );

    expect(screen.getByText(/1 other pathway/)).toBeInTheDocument();
    expect(screen.getByText("Breast")).toBeInTheDocument();
  });

  it("does not render related section when no siblings", () => {
    const ep = withRisk({
      episode_id: "EP-SOLO",
      patient_id: "PAT-B",
      condition_type: "Skin",
      status: "active",
      referral_date: "2026-02-20",
      milestones: [],
    });

    render(
      <EpisodeTimelineView
        episode={ep}
        risk={ep.risk}
        siblingEpisodes={[]}
      />,
    );

    expect(screen.queryByText(/other pathway/)).not.toBeInTheDocument();
  });
});
