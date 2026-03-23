import React from "react";
import { render, screen } from "@testing-library/react";
import BenchmarkLegend from "../BenchmarkLegend";

describe("BenchmarkLegend", () => {
  it("renders all 4 default comparison levels", () => {
    render(<BenchmarkLegend />);
    expect(screen.getByText("This Practice")).toBeInTheDocument();
    expect(screen.getByText("Cancer Alliance (today)")).toBeInTheDocument();
    expect(screen.getByText("All Patients (today)")).toBeInTheDocument();
    expect(screen.getByText("This Practice (2018)")).toBeInTheDocument();
  });

  it("renders only selected keys when visibleKeys provided", () => {
    render(<BenchmarkLegend visibleKeys={["practice", "national"]} />);
    expect(screen.getByText("This Practice")).toBeInTheDocument();
    expect(screen.getByText("This Practice (2018)")).toBeInTheDocument();
    expect(screen.queryByText("Cancer Alliance (today)")).not.toBeInTheDocument();
    expect(screen.queryByText("All Patients (today)")).not.toBeInTheDocument();
  });
});
