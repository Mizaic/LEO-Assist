import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import TrainSection from "../TrainSection";

beforeEach(() => {
  jest.spyOn(global, "fetch").mockImplementation((url, init) => {
    const requestUrl = String(url);
    if (
      requestUrl.includes("/api/training/gold-labels/stats")
    ) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            total: 120,
            high_quality: 95,
            avg_quality_score: 0.88,
          }),
      } as Response);
    }
    if (requestUrl.includes("/api/training-worker/jobs")) {
      if (init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ job_id: "job-123" }),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            jobs: [
              {
                job_id: "job-abc-123",
                status: "done",
                phase: "",
                model_version: "20260412-101010",
                error: "",
                created_at: 0,
                elapsed_s: 12,
              },
            ],
          }),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("VT-036-TC-019: TrainSection plain-language stat cards", () => {
  it("renders gold-label training stats", async () => {
    render(<TrainSection />);
    await waitFor(() => {
      expect(screen.getByText("120 gold labels")).toBeInTheDocument();
    });
    expect(screen.getByText("95 high quality")).toBeInTheDocument();
    expect(screen.getByText("Avg quality: 0.880")).toBeInTheDocument();
  });

  it("links to gold dataset management", async () => {
    render(<TrainSection />);
    await waitFor(() => {
      expect(screen.getByText("Manage training data")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Manage training data" })).toHaveAttribute(
      "href",
      "/admin/knowledge?tab=training-data",
    );
  });

  it("starts a training run", async () => {
    render(<TrainSection />);
    await waitFor(() => {
      expect(screen.getByText("Run training")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Run training"));
    await waitFor(() => {
      expect(screen.getByText("Training started. Job ID: job-123")).toBeInTheDocument();
    });
  });

  it("shows error alert when stats fetch fails", async () => {
    jest.restoreAllMocks();
    jest.spyOn(global, "fetch").mockRejectedValue(new Error("Network error"));
    render(<TrainSection />);
    await waitFor(() => {
      expect(
        screen.getByText("Network error"),
      ).toBeInTheDocument();
    });
  });
});
