import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EpisodeList from "../EpisodeList";
import { assessPathwayRisk, type Episode, type PathwayRisk } from "@/lib/pathwayRisk";

const TODAY = "2026-02-26";

function withRisk(ep: Episode): Episode & { risk: PathwayRisk } {
  return { ...ep, risk: assessPathwayRisk(ep, TODAY) };
}

const breachedEpisode = withRisk({
  episode_id: "EP-BREACH",
  cancer_type: "Lung",
  status: "active",
  referral_date: "2026-01-15",
  milestones: [
    { encounter_id: "E1", date: "2026-01-15", milestone_type: "referral" },
  ],
});

const onTrackEpisode = withRisk({
  episode_id: "EP-TRACK",
  cancer_type: "Breast",
  status: "active",
  referral_date: "2026-02-24",
  milestones: [
    { encounter_id: "E2", date: "2026-02-24", milestone_type: "referral" },
  ],
});

describe("EpisodeList", () => {
  it("renders episode cancer types", () => {
    render(
      <EpisodeList
        episodes={[breachedEpisode, onTrackEpisode]}
        selected={null}
        onSelect={jest.fn()}
      />,
    );
    expect(screen.getByText("Lung")).toBeInTheDocument();
    expect(screen.getByText("Breast")).toBeInTheDocument();
  });

  it("shows risk chip for each episode", () => {
    render(
      <EpisodeList
        episodes={[breachedEpisode, onTrackEpisode]}
        selected={null}
        onSelect={jest.fn()}
      />,
    );
    expect(screen.getByText("Breached")).toBeInTheDocument();
    expect(screen.getByText("On track")).toBeInTheDocument();
  });

  it("shows breach countdown for breached pathway", () => {
    render(
      <EpisodeList
        episodes={[breachedEpisode]}
        selected={null}
        onSelect={jest.fn()}
      />,
    );
    expect(screen.getByText(/overdue/)).toBeInTheDocument();
  });

  it("shows next milestone for active pathway", () => {
    render(
      <EpisodeList
        episodes={[onTrackEpisode]}
        selected={null}
        onSelect={jest.fn()}
      />,
    );
    expect(screen.getByText(/Next:/)).toBeInTheDocument();
  });

  it("calls onSelect when card is clicked", async () => {
    const onSelect = jest.fn();
    const user = userEvent.setup();
    render(
      <EpisodeList
        episodes={[breachedEpisode]}
        selected={null}
        onSelect={onSelect}
      />,
    );
    await user.click(screen.getByText("Lung"));
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ episode_id: "EP-BREACH" }),
    );
  });

  it("shows empty state when no episodes match", () => {
    render(
      <EpisodeList episodes={[]} selected={null} onSelect={jest.fn()} />,
    );
    expect(
      screen.getByText("No referral pathways match your filters."),
    ).toBeInTheDocument();
  });

  it("highlights selected card", () => {
    const { container } = render(
      <EpisodeList
        episodes={[breachedEpisode, onTrackEpisode]}
        selected={breachedEpisode}
        onSelect={jest.fn()}
      />,
    );
    const cards = container.querySelectorAll(".MuiCard-root");
    expect(cards.length).toBe(2);
  });
});
