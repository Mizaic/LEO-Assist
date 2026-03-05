import React from "react";
import { render, screen } from "@testing-library/react";
import BenchmarkLegend from "../BenchmarkLegend";

describe("BenchmarkLegend", () => {
  it("renders all 4 default comparison levels", () => {
    render(<BenchmarkLegend />);
    expect(screen.getByText("This Practice")).toBeInTheDocument();
    expect(screen.getByText("Similar Practices")).toBeInTheDocument();
    expect(screen.getByText("Cancer Alliance")).toBeInTheDocument();
    expect(screen.getByText("England (National)")).toBeInTheDocument();
  });

  it("renders only selected keys when visibleKeys provided", () => {
    render(<BenchmarkLegend visibleKeys={["practice", "national"]} />);
    expect(screen.getByText("This Practice")).toBeInTheDocument();
    expect(screen.getByText("England (National)")).toBeInTheDocument();
    expect(screen.queryByText("Similar Practices")).not.toBeInTheDocument();
    expect(screen.queryByText("Cancer Alliance")).not.toBeInTheDocument();
  });
});
