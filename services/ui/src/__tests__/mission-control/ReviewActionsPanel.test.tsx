/**
 * VT-2487F804 (and legacy VT-LEO-AI-092): verdict-driven sign-off panel.
 *
 * Pins the single-path curator UX introduced by DI-E2498DF6:
 *   - verdict selector is required (Save disabled until a verdict picked)
 *   - Save sign-off calls patchEpisodeSignOff with the chosen verdict
 *   - a reviewed episode renders the verdict chip, not the old "Reviewed by"
 *   - the pre-verdict override button is gone
 */

import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import ReviewActionsPanel from "@/components/mission-control/ReviewActionsPanel";
import type { MissionEpisode } from "@/lib/missionControlApi";
import * as api from "@/lib/missionControlApi";

jest.mock("@/lib/missionControlApi", () => ({
  patchEpisodeSignOff: jest.fn().mockResolvedValue({
    episode_id: "ep-001",
    review_verdict: "confirmed_benign",
    status: "closed_benign",
    reviewed_at: "2026-04-22T09:00:00",
    reviewed_by: "auditor@nhs.net",
  }),
}));

const originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;

beforeAll(() => {
  HTMLElement.prototype.getBoundingClientRect = function mockRect(): DOMRect {
    return {
      x: 0,
      y: 0,
      width: 240,
      height: 40,
      top: 0,
      left: 0,
      right: 240,
      bottom: 40,
      toJSON: () => ({}),
    } as DOMRect;
  };
});

afterAll(() => {
  HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect;
});

async function selectVerdict(optionText: string) {
  const input = screen.getByLabelText("Review verdict");
  const combobox = input.closest('[role="combobox"]') ?? input;
  fireEvent.mouseDown(combobox);
  const listbox = await screen.findByRole("listbox");
  const option = within(listbox).getByText(optionText);
  fireEvent.click(option);
}

const EPISODE: MissionEpisode = {
  episode_id: "ep-001",
  cancer_type: "colorectal",
  condition_type: "cancer",
  status: "review",
  cancer_stage: null,
  referral_date: "2024-06-15",
  end_date: null,
  diagnostic_interval_days: 35,
  benign_interval_days: null,
  primary_care_interval_days: null,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  review_verdict: null,
  audit_notes: null,
  audit_flag: false,
};

describe("ReviewActionsPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("Save sign-off is disabled until a verdict is picked", () => {
    render(
      <ReviewActionsPanel
        episode={EPISODE}
        userEmail="auditor@nhs.net"
        onReviewed={jest.fn()}
      />,
    );
    const save = screen.getByRole("button", { name: /save sign-off/i });
    expect(save).toBeDisabled();
  });

  test("Picking a verdict enables Save and patchEpisodeSignOff is called", async () => {
    const onReviewed = jest.fn();
    render(
      <ReviewActionsPanel
        episode={EPISODE}
        userEmail="auditor@nhs.net"
        onReviewed={onReviewed}
      />,
    );

    await selectVerdict("Confirm ruled out (benign)");

    const save = screen.getByRole("button", { name: /save sign-off/i });
    expect(save).not.toBeDisabled();

    fireEvent.click(save);

    await waitFor(() => {
      expect(api.patchEpisodeSignOff).toHaveBeenCalledTimes(1);
      expect(api.patchEpisodeSignOff).toHaveBeenCalledWith(
        "ep-001",
        expect.objectContaining({
          verdict: "confirmed_benign",
          reviewed_by: "auditor@nhs.net",
        }),
      );
    });

    await waitFor(() => {
      expect(onReviewed).toHaveBeenCalledWith(
        expect.objectContaining({
          review_verdict: "confirmed_benign",
          status: "closed_benign",
        }),
      );
    });
  });

  test("A reviewed episode with verdict shows the verdict chip", () => {
    render(
      <ReviewActionsPanel
        episode={{
          ...EPISODE,
          status: "closed_benign",
          reviewed_by: "rob@nhs.net",
          reviewed_at: "2026-04-22T09:00:00",
          review_verdict: "confirmed_benign",
        }}
        userEmail="auditor@nhs.net"
        onReviewed={jest.fn()}
      />,
    );
    expect(
      screen.getByText(/confirm ruled out \(benign\) by rob@nhs\.net/i),
    ).toBeInTheDocument();
  });

  test("A reviewed episode without verdict shows the 'no verdict' warning chip", () => {
    render(
      <ReviewActionsPanel
        episode={{
          ...EPISODE,
          reviewed_by: "rob@nhs.net",
          reviewed_at: "2026-04-22T09:00:00",
          review_verdict: null,
        }}
        userEmail="auditor@nhs.net"
        onReviewed={jest.fn()}
      />,
    );
    expect(
      screen.getByText(/reviewed by rob@nhs\.net \(no verdict recorded\)/i),
    ).toBeInTheDocument();
  });

  test("The pre-verdict 'Mark as reviewed' and 'Override' controls are gone", () => {
    render(
      <ReviewActionsPanel
        episode={EPISODE}
        userEmail="auditor@nhs.net"
        onReviewed={jest.fn()}
      />,
    );
    expect(screen.queryByText(/mark as reviewed/i)).toBeNull();
    expect(screen.queryByText(/override pathway status/i)).toBeNull();
  });
});
