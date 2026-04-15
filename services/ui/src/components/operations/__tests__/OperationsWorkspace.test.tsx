import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import OperationsWorkspace from "../OperationsWorkspace";

// -- Mock all heavy section components so they don't make their own API calls

jest.mock("../TrainSection", () => ({
  __esModule: true,
  default: () => <div data-testid="train-section">TrainSection</div>,
}));

jest.mock("../QualitySection", () => ({
  __esModule: true,
  default: () => <div data-testid="quality-section">QualitySection</div>,
}));

jest.mock("../ModelLifecyclePanel", () => ({
  __esModule: true,
  default: () => <div data-testid="model-lifecycle-panel">ModelLifecyclePanel</div>,
}));

jest.mock("../RunSection", () => ({
  __esModule: true,
  default: () => <div data-testid="run-section">RunSection</div>,
}));

// -- Fetch helpers

function makeFetch(overrides: {
  pending?: number;
  modelStatus?: string;
  modelVersion?: string;
  unacknowledged?: number;
}) {
  const {
    pending = 0,
    modelStatus = "active",
    modelVersion = "20260301",
    unacknowledged = 0,
  } = overrides;

  return jest.fn().mockImplementation((url: string) => {
    if (url.includes("/api/operations/metrics")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            metrics_by_stage: { coding: { pending, resolved: 5 } },
          }),
      } as Response);
    }
    if (url.includes("/api/model-registry/status")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            active_model: { model_version: modelVersion, status: modelStatus },
          }),
      } as Response);
    }
    if (url.includes("/api/operations/quality/alerts/count")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ unacknowledged }),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

// -- Tests -------------------------------------------------------------------

describe("OperationsWorkspace: section accordion", () => {
  it("renders operations workflow section headers", async () => {
    global.fetch = makeFetch({});
    render(<OperationsWorkspace initialTab="train" />);
    await waitFor(() => expect(screen.getByText("Training data")).toBeInTheDocument());
    expect(screen.getByText("How is it doing?")).toBeInTheDocument();
    expect(screen.getByText("Make it live")).toBeInTheDocument();
    expect(screen.getByText("Process patients")).toBeInTheDocument();
  });

  it("does not render the legacy fix and teach headers", async () => {
    global.fetch = makeFetch({});
    render(<OperationsWorkspace initialTab="train" />);
    await waitFor(() => expect(screen.getByText("Training data")).toBeInTheDocument());
    expect(screen.queryByText("Fix mistakes")).not.toBeInTheDocument();
    expect(screen.queryByText("Teach the AI")).not.toBeInTheDocument();
  });

  it("shows the page heading and sub-heading", async () => {
    global.fetch = makeFetch({});
    render(<OperationsWorkspace />);
    expect(screen.getByRole("heading", { name: /Operations/i })).toBeInTheDocument();
    expect(screen.getByText(/Manage, improve and monitor the AI/i)).toBeInTheDocument();
  });
});

describe("OperationsWorkspace: context banner", () => {
  it("shows an info banner when no AI is live", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "pending" });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/Check the gold dataset and start a training run/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /Open training data/i }),
    ).toBeInTheDocument();
  });

  it("shows a quality alert warning when there are unacknowledged alerts", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active", unacknowledged: 3 });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/3 quality alerts/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /Check now/i })).toBeInTheDocument();
  });

  it("shows a success banner when everything is good", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active", unacknowledged: 0 });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/Everything looks good/i)).toBeInTheDocument(),
    );
  });
});

describe("OperationsWorkspace: accordion interaction", () => {
  it("collapses an open section on second click", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "pending" });
    render(<OperationsWorkspace />);
    await waitFor(() => expect(screen.getByTestId("train-section")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Training data").closest("button")!);
    await waitFor(() =>
      expect(screen.queryByTestId("train-section")).not.toBeInTheDocument(),
    );
  });

  it("auto-opens Training data when no model is live", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "pending" });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByTestId("train-section")).toBeInTheDocument(),
    );
  });

  it("auto-opens Make it live when all is clear", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active", unacknowledged: 0 });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByTestId("model-lifecycle-panel")).toBeInTheDocument(),
    );
  });

  it("respects the initialTab prop to pre-open a section", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active" });
    render(<OperationsWorkspace initialTab="quality" />);
    await waitFor(() =>
      expect(screen.getByTestId("quality-section")).toBeInTheDocument(),
    );
  });

  it("maps legacy initialTab value 'review' to Training data section", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active" });
    render(<OperationsWorkspace initialTab="review" />);
    await waitFor(() =>
      expect(screen.getByTestId("train-section")).toBeInTheDocument(),
    );
  });
});

describe("OperationsWorkspace: status labels", () => {
  it("shows training section status text", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active" });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(
        screen.getByText("Manage gold labels and run training"),
      ).toBeInTheDocument(),
    );
  });

  it("shows model version in Make it live status when model is active", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active", modelVersion: "1.2.3" });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/v1\.2\.3 is live/i)).toBeInTheDocument(),
    );
  });

  it("shows No AI is live yet when no active model", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "pending" });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText("No AI is live yet")).toBeInTheDocument(),
    );
  });
});
