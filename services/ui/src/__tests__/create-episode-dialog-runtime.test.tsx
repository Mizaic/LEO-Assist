// Runtime check for CreateEpisodeDialog: clicking the "Create
// episode" button must invoke createEpisode().
//
// This guards against the regression reported as "I click Create and
// nothing happens / no POST in the Network tab".

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

jest.mock("@/lib/missionControlApi", () => ({
  createEpisode: jest.fn(),
}));

import { createEpisode } from "@/lib/missionControlApi";
import CreateEpisodeDialog from "@/components/mission-control/CreateEpisodeDialog";

describe("CreateEpisodeDialog runtime", () => {
  beforeEach(() => {
    (createEpisode as jest.Mock).mockReset();
    (createEpisode as jest.Mock).mockResolvedValue({
      success: true,
      episode_id: "ep-manual-abc123",
      patient_id: "pat-1",
      derived_dates: null,
    });
  });

  it("invokes createEpisode when the Create button is clicked", async () => {
    const onClose = jest.fn();
    const onCreated = jest.fn();
    render(
      <CreateEpisodeDialog
        open
        patientId="pat-1"
        reviewerRole="clinician"
        onClose={onClose}
        onCreated={onCreated}
      />,
    );

    const button = screen.getByTestId("create-episode-confirm");
    expect(button).not.toBeDisabled();
    fireEvent.click(button);

    await waitFor(() => {
      expect(createEpisode).toHaveBeenCalledTimes(1);
    });
    const body = (createEpisode as jest.Mock).mock.calls[0][0];
    expect(body.patient_id).toBe("pat-1");
    expect(body.status).toBe("review");
    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith("ep-manual-abc123");
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("disables Create when the role is not a curator", () => {
    render(
      <CreateEpisodeDialog
        open
        patientId="pat-1"
        reviewerRole="reviewer"
        onClose={jest.fn()}
        onCreated={jest.fn()}
      />,
    );
    expect(screen.getByTestId("create-episode-confirm")).toBeDisabled();
  });
});
