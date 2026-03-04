import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import DeploySection from "../DeploySection";

jest.mock("../ModelLifecyclePanel", () => {
  return function MockPanel() {
    return <div data-testid="model-lifecycle-panel" />;
  };
});

const activeModel = {
  model_name: "ner",
  model_version: "4",
  status: "active",
  offline_precision: 0.92,
  offline_recall: 0.88,
  canary_precision: 0.9,
  canary_recall: 0.85,
  registered_at: "2026-03-01T10:00:00Z",
  promoted_at: "2026-03-02T12:00:00Z",
  notes: null,
};

beforeEach(() => {
  jest.spyOn(global, "fetch").mockImplementation(() =>
    Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          active_model: activeModel,
          total_versions: 4,
        }),
    } as Response),
  );
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("VT-036-TC-022: DeploySection plain-language metric labels", () => {
  it("renders plain-language status label", async () => {
    render(<DeploySection />);
    await waitFor(() => {
      expect(screen.getByText(/Current AI: version 4/)).toBeInTheDocument();
    });
  });

  it("uses plain metric labels instead of ML jargon", async () => {
    render(<DeploySection />);
    await waitFor(() => {
      expect(screen.getByText("Training accuracy")).toBeInTheDocument();
    });
    expect(screen.getByText("Training completeness")).toBeInTheDocument();
    expect(screen.getByText("Live test accuracy")).toBeInTheDocument();
    expect(screen.getByText("Live test completeness")).toBeInTheDocument();
  });

  it("does not show ML jargon metric labels", async () => {
    render(<DeploySection />);
    await waitFor(() => {
      expect(screen.getByText("Training accuracy")).toBeInTheDocument();
    });
    expect(screen.queryByText("Offline precision")).not.toBeInTheDocument();
    expect(screen.queryByText("Offline recall")).not.toBeInTheDocument();
    expect(screen.queryByText("Canary precision")).not.toBeInTheDocument();
    expect(screen.queryByText("Canary recall")).not.toBeInTheDocument();
  });

  it("shows empty state with plain language when no model", async () => {
    jest.restoreAllMocks();
    jest.spyOn(global, "fetch").mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ active_model: null, total_versions: 0 }),
      } as Response),
    );
    render(<DeploySection />);
    await waitFor(() => {
      expect(screen.getByText("No AI is live yet")).toBeInTheDocument();
    });
    expect(
      screen.getByText("Teach and test an AI, then make it live."),
    ).toBeInTheDocument();
  });

  it("shows error alert when fetch fails", async () => {
    jest.restoreAllMocks();
    jest.spyOn(global, "fetch").mockImplementation(() =>
      Promise.resolve({ ok: false, status: 500 } as Response),
    );
    render(<DeploySection />);
    await waitFor(() => {
      expect(
        screen.getByText("Could not load AI information. Please try again."),
      ).toBeInTheDocument();
    });
  });
});
