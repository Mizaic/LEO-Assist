import React from "react";
import { render, screen } from "@testing-library/react";
import CancerTypeDumbbellChart, {
  humaniseCancerLabel,
  type DumbbellRow,
} from "../CancerTypeDumbbellChart";

// VT-LEO-AI-090

// ResizeObserver is not available in jsdom — provide a no-op stub.
beforeAll(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const rowsWithBenchmark: DumbbellRow[] = [
  { cancer_type: "breast", practice: 30.2, national: 15.3 },
  { cancer_type: "lung",   practice: 2.5,  national: 13.2 },
];

const rowsNoBenchmark: DumbbellRow[] = [
  { cancer_type: "breast", practice: 30.2, national: null },
  { cancer_type: "lung",   practice: 2.5,  national: null },
];

const rowsUnderscore: DumbbellRow[] = [
  { cancer_type: "lower_gi",        practice: 14.8, national: 11.7 },
  { cancer_type: "head_and_neck",   practice: 9.1,  national: 7.5  },
  { cancer_type: "non_site_specific", practice: 4.0, national: 4.8 },
];

// VT-090-TC-001: renders one row per cancer type
describe("CancerTypeDumbbellChart", () => {
  it("renders one row per cancer type", () => {
    render(<CancerTypeDumbbellChart rows={rowsWithBenchmark} />);
    expect(screen.getByText("Breast")).toBeInTheDocument();
    expect(screen.getByText("Lung")).toBeInTheDocument();
  });

  // VT-090-TC-002: empty state
  it("shows empty state when rows array is empty", () => {
    render(<CancerTypeDumbbellChart rows={[]} />);
    expect(screen.getByText(/no cancer type data/i)).toBeInTheDocument();
  });

  // VT-090-TC-003: humanises underscore keys
  it("humanises underscore key strings as labels", () => {
    render(<CancerTypeDumbbellChart rows={rowsUnderscore} />);
    expect(screen.getByText("Lower GI")).toBeInTheDocument();
    expect(screen.getByText("Head and Neck")).toBeInTheDocument();
    expect(screen.getByText("Non Site Specific")).toBeInTheDocument();
  });

  // VT-090-TC-004: delta label shows +pp above benchmark
  it("shows a positive delta label when practice exceeds benchmark", () => {
    render(<CancerTypeDumbbellChart rows={rowsWithBenchmark} />);
    // breast: 30.2 - 15.3 = +14.9pp
    expect(screen.getByText("+14.9pp")).toBeInTheDocument();
  });

  // VT-090-TC-005: delta label shows -pp below benchmark
  it("shows a negative delta label when practice is below benchmark", () => {
    render(<CancerTypeDumbbellChart rows={rowsWithBenchmark} />);
    // lung: 2.5 - 13.2 = -10.7pp
    expect(screen.getByText("-10.7pp")).toBeInTheDocument();
  });

  // VT-090-TC-006: no delta label when benchmark is null
  it("does not render any pp delta label when all benchmarks are null", () => {
    render(<CancerTypeDumbbellChart rows={rowsNoBenchmark} />);
    expect(screen.queryByText(/pp/)).not.toBeInTheDocument();
  });

  // VT-090-TC-007: renders without error when all benchmarks are null
  it("renders without throwing when all benchmarks are null", () => {
    expect(() =>
      render(<CancerTypeDumbbellChart rows={rowsNoBenchmark} />)
    ).not.toThrow();
    expect(screen.getByText("Breast")).toBeInTheDocument();
    expect(screen.getByText("Lung")).toBeInTheDocument();
  });

  // humaniseCancerLabel unit tests
  describe("humaniseCancerLabel", () => {
    it("returns special-case label for lower_gi", () => {
      expect(humaniseCancerLabel("lower_gi")).toBe("Lower GI");
    });

    it("returns special-case label for cns", () => {
      expect(humaniseCancerLabel("cns")).toBe("CNS");
    });

    it("title-cases plain single-word keys", () => {
      expect(humaniseCancerLabel("breast")).toBe("Breast");
      expect(humaniseCancerLabel("lung")).toBe("Lung");
    });

    it("title-cases and spaces multi-word keys not in lookup", () => {
      expect(humaniseCancerLabel("haematological")).toBe("Haematological");
      expect(humaniseCancerLabel("upper_gi")).toBe("Upper GI");
    });
  });
});
