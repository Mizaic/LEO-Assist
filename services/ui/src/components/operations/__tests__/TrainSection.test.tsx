import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import TrainSection from "../TrainSection";

jest.mock("../TrainingDataPanel", () => {
  return function MockPanel() {
    return <div data-testid="training-data-panel" />;
  };
});
jest.mock("../LabelVerificationPanel", () => {
  return function MockPanel() {
    return <div data-testid="label-verification-panel" />;
  };
});

beforeEach(() => {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    if (typeof url === "string" && url.includes("/api/training/labels/stats")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ total: 120, included: 100, excluded: 20, by_source: {} }),
      } as Response);
    }
    if (typeof url === "string" && url.includes("/api/training/coding-review/stats")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ total: 50, coded: 40, uncoded: 10, resolved: 30, pending: 20 }),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("VT-036-TC-019: TrainSection plain-language stat cards", () => {
  it("renders stat cards with plain-language titles", async () => {
    render(<TrainSection />);
    await waitFor(() => {
      expect(screen.getByText("Teaching examples")).toBeInTheDocument();
    });
    expect(screen.getByText("Checked records")).toBeInTheDocument();
    expect(screen.getByText("Need attention")).toBeInTheDocument();
  });

  it("does not use ML jargon in card titles", async () => {
    render(<TrainSection />);
    await waitFor(() => {
      expect(screen.getByText("Teaching examples")).toBeInTheDocument();
    });
    expect(screen.queryByText("Training labels")).not.toBeInTheDocument();
    expect(screen.queryByText("Coding reviews")).not.toBeInTheDocument();
    expect(screen.queryByText("Uncoded items")).not.toBeInTheDocument();
  });

  it("renders sub-tabs with plain labels", () => {
    render(<TrainSection />);
    expect(screen.getByText("Teach the AI")).toBeInTheDocument();
    expect(screen.getByText("Check the labels")).toBeInTheDocument();
  });

  it("does not use ML jargon in tab labels", () => {
    render(<TrainSection />);
    expect(screen.queryByText("Training data")).not.toBeInTheDocument();
    expect(screen.queryByText("Label checks")).not.toBeInTheDocument();
  });

  it("shows error alert when stats fetch fails", async () => {
    jest.restoreAllMocks();
    jest.spyOn(global, "fetch").mockRejectedValue(new Error("Network error"));
    render(<TrainSection />);
    await waitFor(() => {
      expect(
        screen.getByText("Could not load training information. Please try again."),
      ).toBeInTheDocument();
    });
  });

  it("renders hint text on stat cards", async () => {
    render(<TrainSection />);
    await waitFor(() => {
      expect(screen.getByText("Records the AI learns from")).toBeInTheDocument();
    });
    expect(screen.getByText("Records reviewed by a person")).toBeInTheDocument();
  });
});
