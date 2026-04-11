import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import OperationsWorkspace from "../OperationsWorkspace";

// -- Mock all heavy section components so they don't make their own API calls

jest.mock("../ReviewSection", () => ({
  __esModule: true,
  default: () => <div data-testid="review-section">ReviewSection</div>,
}));

jest.mock("../TrainSection", () => ({
  __esModule: true,
  default: () => <div data-testid="train-section">TrainSection</div>,
}));

jest.mock("../QualitySection", () => ({
  __esModule: true,
  default: () => <div data-testid="quality-section">QualitySection</div>,
}));

jest.mock("../DeploySection", () => ({
  __esModule: true,
  default: () => <div data-testid="deploy-section">DeploySection</div>,
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
  it("renders all four workflow section headers", async () => {
    global.fetch = makeFetch({});
    render(<OperationsWorkspace />);
    await waitFor(() => expect(screen.getByText("Fix mistakes")).toBeInTheDocument());
    expect(screen.getByText("Teach the AI")).toBeInTheDocument();
    expect(screen.getByText("How is it doing?")).toBeInTheDocument();
    expect(screen.getByText("Make it live")).toBeInTheDocument();
    expect(screen.getByText("Process patients")).toBeInTheDocument();
  });

  it("uses no technical jargon in section headers", async () => {
    global.fetch = makeFetch({});
    render(<OperationsWorkspace />);
    await waitFor(() => expect(screen.getByText("Fix mistakes")).toBeInTheDocument());
    expect(screen.queryByText("Review")).not.toBeInTheDocument();
    expect(screen.queryByText("Train")).not.toBeInTheDocument();
    expect(screen.queryByText("Quality")).not.toBeInTheDocument();
    expect(screen.queryByText("Deploy")).not.toBeInTheDocument();
    expect(screen.queryByText("Run pipeline")).not.toBeInTheDocument();
  });

  it("shows the page heading and sub-heading", async () => {
    global.fetch = makeFetch({});
    render(<OperationsWorkspace />);
    expect(screen.getByRole("heading", { name: /Operations/i })).toBeInTheDocument();
    expect(screen.getByText(/Manage, improve and monitor the AI/i)).toBeInTheDocument();
  });
});

describe("OperationsWorkspace: context banner", () => {
  it("shows a warning banner when there are pending review items", async () => {
    global.fetch = makeFetch({ pending: 7 });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/7 things to fix/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /Fix them now/i })).toBeInTheDocument();
  });

  it("shows a singular warning banner when there is 1 pending review item", async () => {
    global.fetch = makeFetch({ pending: 1 });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/1 thing to fix/i)).toBeInTheDocument(),
    );
  });

  it("shows an info banner when no AI is live", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "pending" });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/The AI is not live yet/i)).toBeInTheDocument(),
    );
    // "Teach the AI" appears as both the banner action button and the section header button
    const teachButtons = screen.getAllByRole("button", { name: /Teach the AI/i });
    expect(teachButtons.length).toBeGreaterThanOrEqual(1);
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
  it("opens Fix mistakes section on click when stats show pending items", async () => {
    global.fetch = makeFetch({ pending: 5 });
    render(<OperationsWorkspace />);
    await waitFor(() => expect(screen.getByText("Fix mistakes")).toBeInTheDocument());
    // The section should be auto-open; ReviewSection should be visible
    await waitFor(() =>
      expect(screen.getByTestId("review-section")).toBeInTheDocument(),
    );
  });

  it("collapses an open section on second click", async () => {
    global.fetch = makeFetch({ pending: 5 });
    render(<OperationsWorkspace />);
    await waitFor(() => expect(screen.getByTestId("review-section")).toBeInTheDocument());
    // Click the already-open "Fix mistakes" header to close it
    fireEvent.click(screen.getByText("Fix mistakes").closest("button")!);
    await waitFor(() =>
      expect(screen.queryByTestId("review-section")).not.toBeInTheDocument(),
    );
  });

  it("auto-opens Teach the AI when no model is live and no pending items", async () => {
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
      expect(screen.getByTestId("deploy-section")).toBeInTheDocument(),
    );
  });

  it("respects the initialTab prop to pre-open a section", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active" });
    render(<OperationsWorkspace initialTab="quality" />);
    await waitFor(() =>
      expect(screen.getByTestId("quality-section")).toBeInTheDocument(),
    );
  });

  it("maps legacy initialTab value 'review' to Fix mistakes section", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active" });
    render(<OperationsWorkspace initialTab="review" />);
    await waitFor(() =>
      expect(screen.getByTestId("review-section")).toBeInTheDocument(),
    );
  });
});

describe("OperationsWorkspace: status labels", () => {
  it("shows pending count as status label under Fix mistakes", async () => {
    global.fetch = makeFetch({ pending: 12 });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/12 things need fixing/i)).toBeInTheDocument(),
    );
  });

  it("shows All done under Fix mistakes when queue is empty", async () => {
    global.fetch = makeFetch({ pending: 0, modelStatus: "active" });
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText("All done")).toBeInTheDocument(),
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
