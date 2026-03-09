import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import AdminOperationsPage from "../page";

const push = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("Operations dashboard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(global, "fetch").mockImplementation((url) => {
      if (typeof url === "string" && url.includes("/api/operations/metrics")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            metrics_by_stage: { coding: { pending: 3 } },
            surface_form_tasks_pending: 2,
            training_candidates: 8,
            gold_labels: 5,
          }),
        } as Response);
      }
      if (typeof url === "string" && url.includes("/api/model-registry/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ active_model: { model_version: "1.2.3", status: "active" } }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders the current operations cards", async () => {
    render(<AdminOperationsPage />);
    await waitFor(() => expect(screen.getByText("Run the AI")).toBeInTheDocument());
    expect(screen.getByText("Things to check")).toBeInTheDocument();
    expect(screen.getByText("Verification examples")).toBeInTheDocument();
  });
});

