/**
 * Jest tests for the Mission Control VariationPanel.
 *
 * Atlas trace: VT-3B37176C -- verifies that the panel surfaces the
 * variation_flag / variation_score / outlier steps / attribution that
 * the scorer writes back to the episode, including the "within peer
 * range" and "hidden" states.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import VariationPanel from "@/components/mission-control/VariationPanel";
import * as api from "@/lib/missionControlApi";
import type { MissionEpisode } from "@/lib/missionControlApi";

jest.mock("@/lib/missionControlApi", () => {
  const actual = jest.requireActual("@/lib/missionControlApi");
  return {
    ...actual,
    fetchEpisodeVariation: jest.fn(),
  };
});

const fetchMock = api.fetchEpisodeVariation as jest.MockedFunction<
  typeof api.fetchEpisodeVariation
>;

const BASE_EPISODE: MissionEpisode = {
  episode_id: "ep-001",
  cancer_type: "colorectal",
  condition_type: "cancer",
  status: "review",
  cancer_stage: null,
  referral_date: "2026-01-01",
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
  milestones: [],
};

beforeEach(() => {
  fetchMock.mockReset();
});

describe("VariationPanel", () => {
  test("renders nothing when episode has no variation signals", () => {
    const { container } = render(<VariationPanel episode={BASE_EPISODE} />);
    expect(container).toBeEmptyDOMElement();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("shows flagged chip with score when episode is flagged", async () => {
    fetchMock.mockResolvedValue({
      episode_id: "ep-001",
      community_id: 7,
      variation_flag: true,
      variation_score: 0.5,
      variation_first_divergence: "referral->first_seen",
      variation_outlier_steps: ["referral->first_seen"],
      variation_attributed_node_type: "GPPractice",
      variation_attributed_node_id: "gp-9",
      variation_attributed_node_name: "Acme Surgery",
      cohort_size: 42,
      cohort_percentiles: [
        {
          from_step: "referral",
          to_step: "first_seen",
          p25: 5,
          p50: 10,
          p75: 20,
          sample_size: 42,
        },
      ],
    });

    const flagged: MissionEpisode = {
      ...BASE_EPISODE,
      variation_flag: true,
      variation_score: 0.5,
      variation_community_id: 7,
    };

    render(<VariationPanel episode={flagged} />);

    expect(screen.getByText("Pathway variation")).toBeInTheDocument();
    expect(
      screen.getByText(/Flagged - 50% of pairs above peer P75/)
    ).toBeInTheDocument();
    expect(screen.getByText(/Peer cohort #7/)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Acme Surgery (GPPractice)")).toBeInTheDocument();
    });
    expect(screen.getByText(/referral -> first_seen/)).toBeInTheDocument();
    expect(screen.getByText(/peer median 10 days/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("ep-001");
  });

  test("shows 'Within peer range' chip when episode was scored but not flagged", async () => {
    fetchMock.mockResolvedValue({
      episode_id: "ep-ok",
      community_id: 3,
      variation_flag: false,
      variation_score: 0,
      variation_first_divergence: null,
      variation_outlier_steps: [],
      variation_attributed_node_type: null,
      variation_attributed_node_id: null,
      variation_attributed_node_name: null,
      cohort_size: 30,
      cohort_percentiles: [],
    });

    const ok: MissionEpisode = {
      ...BASE_EPISODE,
      episode_id: "ep-ok",
      variation_flag: false,
      variation_score: 0,
      variation_community_id: 3,
    };

    render(<VariationPanel episode={ok} />);

    expect(screen.getByText("Within peer range")).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("ep-ok");
    });
    expect(
      screen.queryByText(/Slower than peer cohort on these steps/)
    ).not.toBeInTheDocument();
  });

  test("renders an error message when the detail fetch fails", async () => {
    fetchMock.mockRejectedValue(new Error("boom"));

    const flagged: MissionEpisode = {
      ...BASE_EPISODE,
      variation_flag: true,
      variation_score: 1,
      variation_community_id: 9,
    };

    render(<VariationPanel episode={flagged} />);

    await waitFor(() => {
      expect(screen.getByText("boom")).toBeInTheDocument();
    });
  });
});
