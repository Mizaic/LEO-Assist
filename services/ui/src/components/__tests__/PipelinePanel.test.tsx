import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PipelinePanel from "../PipelinePanel";

const mockStart = jest.fn();
const mockPipeline = {
  running: false,
  status: null,
  live: null,
  result: null,
  error: null,
  workerStates: {},
  start: mockStart,
  cancel: jest.fn(),
  showModal: false,
  setShowModal: jest.fn(),
};

jest.mock("@/context/PipelineContext", () => ({
  usePipeline: () => mockPipeline,
}));

jest.mock("@/lib/api", () => ({
  exportMedSpaCyTraining: jest.fn(),
}));

import { exportMedSpaCyTraining } from "@/lib/api";

describe("PipelinePanel", () => {
  beforeEach(() => {
    mockStart.mockClear();
    mockPipeline.running = false;
    mockPipeline.result = null;
    mockPipeline.error = null;
  });

  it("renders Process Records and Export sections", () => {
    render(<PipelinePanel />);
    expect(screen.getByRole("heading", { name: "Process Records" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Export Training Data" })).toBeInTheDocument();
  });

  it("Run button is disabled when no patient IDs entered", () => {
    render(<PipelinePanel />);
    expect(screen.getByRole("button", { name: /Process Records/ })).toBeDisabled();
  });

  it("enables Run button when patient IDs are entered", async () => {
    const user = userEvent.setup();
    render(<PipelinePanel />);
    await user.type(screen.getByLabelText(/Patient IDs/), "P001");
    expect(screen.getByRole("button", { name: /Process Records/ })).toBeEnabled();
  });

  it("calls pipeline.start on Run button click", async () => {
    const user = userEvent.setup();
    render(<PipelinePanel />);
    await user.type(screen.getByLabelText(/Patient IDs/), "P001");
    await user.click(screen.getByRole("button", { name: /Process Records/ }));
    expect(mockStart).toHaveBeenCalledWith(
      expect.objectContaining({ patientIds: ["P001"] }),
    );
  });

  it("shows result summary after pipeline completes", () => {
    mockPipeline.result = {
      run_id: "R1",
      processed_encounters: 10,
      queued_for_review: 8,
      rejected_hard_fail: 1,
      warnings_only: 1,
    };
    render(<PipelinePanel />);
    expect(screen.getByText(/Processed: 10/)).toBeInTheDocument();
    expect(screen.getByText(/Queued: 8/)).toBeInTheDocument();
  });

  it("shows error message on pipeline error", () => {
    mockPipeline.error = "Pipeline crashed";
    render(<PipelinePanel />);
    expect(screen.getByText("Pipeline crashed")).toBeInTheDocument();
  });

  it("calls export API when export button is clicked", async () => {
    const user = userEvent.setup();
    (exportMedSpaCyTraining as jest.Mock).mockResolvedValue({
      export_id: "X1",
      entity_count: 50,
      kb_count: 20,
      encounter_count: 10,
    });
    render(<PipelinePanel />);
    await user.click(screen.getByRole("button", { name: /Export training data/ }));
    expect(exportMedSpaCyTraining).toHaveBeenCalled();
  });
});
