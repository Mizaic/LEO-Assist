/**
 * VT-LEO-AI-092 TC-005: ReviewActionsPanel ConfirmDialog guard.
 */

import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import ReviewActionsPanel from "@/components/mission-control/ReviewActionsPanel";
import type { MissionEpisode } from "@/lib/missionControlApi";
import * as api from "@/lib/missionControlApi";

jest.mock("@/lib/missionControlApi", () => ({
  patchEpisodeReview: jest.fn().mockResolvedValue({ episode_id: "ep-001", status: "reviewed" }),
  patchEpisodeStatus: jest.fn().mockResolvedValue(undefined),
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

/** Helper: open MUI Select and choose an option by visible label. */
async function selectMuiOption(labelText: string, optionText: string) {
  const input = screen.getByLabelText(labelText);
  // Click the combobox/select control
  const combobox = input.closest('[role="combobox"]') ?? input;
  fireEvent.mouseDown(combobox);
  // Wait for the listbox to appear
  const listbox = await screen.findByRole("listbox");
  const option = within(listbox).getByText(optionText);
  fireEvent.click(option);
}

const EPISODE: MissionEpisode = {
  episode_id: "ep-001",
  cancer_type: "colorectal",
  condition_type: "cancer",
  status: "completed",
  cancer_stage: null,
  referral_date: "2024-06-15",
  end_date: null,
  diagnostic_interval_days: 35,
  primary_care_interval_days: null,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  audit_notes: null,
  audit_flag: false,
};

describe("ReviewActionsPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders 'Mark as reviewed' button for unreviewed episode", () => {
    render(
      <ReviewActionsPanel
        episode={EPISODE}
        userEmail="auditor@nhs.net"
        onReviewed={jest.fn()}
      />
    );
    expect(screen.getByText("Mark as reviewed")).toBeInTheDocument();
  });

  test("clicking Mark as reviewed calls patchEpisodeReview", async () => {
    const onReviewed = jest.fn();
    render(
      <ReviewActionsPanel
        episode={EPISODE}
        userEmail="auditor@nhs.net"
        onReviewed={onReviewed}
      />
    );

    fireEvent.click(screen.getByText("Mark as reviewed"));

    await waitFor(() => {
      expect(api.patchEpisodeReview).toHaveBeenCalledTimes(1);
      expect(api.patchEpisodeReview).toHaveBeenCalledWith("ep-001", expect.objectContaining({
        reviewed_by: "auditor@nhs.net",
      }));
    });
  });

  test("status override shows ConfirmDialog before calling patchEpisodeStatus", async () => {
    render(
      <ReviewActionsPanel
        episode={EPISODE}
        userEmail="auditor@nhs.net"
        onReviewed={jest.fn()}
      />
    );

    await selectMuiOption("Override pathway status", "No cancer found");
    fireEvent.click(screen.getByText("Override"));

    // ConfirmDialog should appear
    expect(screen.getByText("Override pathway status?")).toBeInTheDocument();
    expect(api.patchEpisodeStatus).not.toHaveBeenCalled();
  });

  test("clicking Cancel in ConfirmDialog prevents patchEpisodeStatus call", async () => {
    render(
      <ReviewActionsPanel
        episode={EPISODE}
        userEmail="auditor@nhs.net"
        onReviewed={jest.fn()}
      />
    );

    await selectMuiOption("Override pathway status", "No cancer found");
    fireEvent.click(screen.getByText("Override"));

    // Cancel the dialog
    fireEvent.click(screen.getByText("Cancel"));

    await waitFor(() => {
      expect(api.patchEpisodeStatus).not.toHaveBeenCalled();
    });
  });

  test("clicking Confirm in ConfirmDialog calls patchEpisodeStatus exactly once", async () => {
    const onReviewed = jest.fn();
    render(
      <ReviewActionsPanel
        episode={EPISODE}
        userEmail="auditor@nhs.net"
        onReviewed={onReviewed}
      />
    );

    await selectMuiOption("Override pathway status", "No cancer found");
    fireEvent.click(screen.getByText("Override"));
    fireEvent.click(screen.getByText("Yes, override"));

    await waitFor(() => {
      expect(api.patchEpisodeStatus).toHaveBeenCalledTimes(1);
      expect(api.patchEpisodeStatus).toHaveBeenCalledWith("ep-001", "closed_benign", expect.any(String));
    });
  });
});
