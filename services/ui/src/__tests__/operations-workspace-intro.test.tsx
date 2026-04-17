import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import fs from "fs";
import path from "path";
import OperationsWorkspace, {
  OPERATIONS_INTRO,
} from "../components/operations/OperationsWorkspace";
import { fleschKincaidGrade } from "../lib/readability";

jest.mock("../components/operations/TrainSection", () => ({
  __esModule: true,
  default: () => <div data-testid="train-section" />,
}));
jest.mock("../components/operations/QualitySection", () => ({
  __esModule: true,
  default: () => <div data-testid="quality-section" />,
}));
jest.mock("../components/operations/ModelLifecyclePanel", () => ({
  __esModule: true,
  default: () => <div data-testid="model-lifecycle-panel" />,
}));
jest.mock("../components/operations/RunSection", () => ({
  __esModule: true,
  default: () => <div data-testid="run-section" />,
}));

function makeFetch() {
  return jest.fn().mockImplementation((url: string) => {
    if (url.includes("/api/operations/metrics")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ metrics_by_stage: { coding: { resolved: 0 } } }),
      } as Response);
    }
    if (url.includes("/api/model-registry/status")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            active_model: { model_version: "1.0.0", status: "active" },
          }),
      } as Response);
    }
    if (url.includes("/api/operations/quality/alerts/count")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ unacknowledged: 0 }),
      } as Response);
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response);
  });
}

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
});

describe("VT-117-TC-001 PageIntro renders on Operations", () => {
  it("renders with screenId='admin-operations'", async () => {
    global.fetch = makeFetch();
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/control room for the AI/i)).toBeInTheDocument(),
    );
    const intro = document.getElementById("admin-operations-intro-title");
    expect(intro).not.toBeNull();
    expect(intro?.tagName.toLowerCase()).toBe("h2");
  });

  it("collapses when the user clicks Hide details and persists", async () => {
    global.fetch = makeFetch();
    render(<OperationsWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/control room for the AI/i)).toBeInTheDocument(),
    );
    const toggle = screen.getByRole("button", { name: /Hide details/i });
    fireEvent.click(toggle);
    expect(window.localStorage.getItem("leo-pageintro-admin-operations")).toBe(
      "collapsed",
    );
  });
});

describe("VT-117-TC-002 PageIntro copy passes Flesch-Kincaid grade <=9", () => {
  it.each(Object.entries(OPERATIONS_INTRO))(
    "%s copy reads at grade <=9",
    (_key, value) => {
      expect(fleschKincaidGrade(value)).toBeLessThanOrEqual(9);
    },
  );
});

describe("VT-117-TC-003 SectionRow exposes aria-expanded + aria-controls", () => {
  it("toggles aria-expanded and points aria-controls at the region", async () => {
    global.fetch = makeFetch();
    render(<OperationsWorkspace initialTab="train" />);
    await waitFor(() =>
      expect(screen.getByTestId("train-section")).toBeInTheDocument(),
    );
    const trigger = screen.getByText("Training data").closest("button")!;
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const controls = trigger.getAttribute("aria-controls");
    expect(controls).toBe("ops-section-train");
    const region = document.getElementById(controls!);
    expect(region).not.toBeNull();
    expect(region?.getAttribute("role")).toBe("region");

    fireEvent.click(trigger);
    await waitFor(() =>
      expect(trigger.getAttribute("aria-expanded")).toBe("false"),
    );
  });
});

describe("VT-117-TC-004 local StatusDot is removed", () => {
  it("components/operations/StatusDot.tsx no longer exists", () => {
    const localStatusDot = path.resolve(
      __dirname,
      "..",
      "components",
      "operations",
      "StatusDot.tsx",
    );
    expect(fs.existsSync(localStatusDot)).toBe(false);
  });
});
