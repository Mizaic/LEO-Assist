import React from "react";
import { render, screen } from "@testing-library/react";
import ComparisonBarChart from "../ComparisonBarChart";
import type { ComparisonDataRow } from "../ComparisonBarChart";

const sampleData: ComparisonDataRow[] = [
  { category: "Breast", practice: 27.5, alliance: 16.6, national: 15.3 },
  { category: "Lung", practice: 15.7, alliance: 11.7, national: 12.6 },
];

describe("ComparisonBarChart", () => {
  it("renders without crashing with valid data", () => {
    render(<ComparisonBarChart data={sampleData} unit="percent" />);
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("renders empty state when no data", () => {
    render(<ComparisonBarChart data={[]} unit="percent" />);
    expect(screen.getByText(/No data available/)).toBeInTheDocument();
  });

  it("renders with horizontal layout", () => {
    render(
      <ComparisonBarChart
        data={sampleData}
        unit="percent"
        layout="horizontal"
        visibleKeys={["practice", "national"]}
      />,
    );
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("applies custom ariaLabel", () => {
    render(
      <ComparisonBarChart
        data={sampleData}
        unit="percent"
        ariaLabel="Cancer type comparison"
      />,
    );
    expect(screen.getByLabelText("Cancer type comparison")).toBeInTheDocument();
  });
});
