import React from "react";
import { render, screen } from "@testing-library/react";
import EpisodesByTypeChart from "../EpisodesByTypeChart";

jest.mock("recharts", () => {
  const Original = jest.requireActual("recharts");
  return {
    ...Original,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container">{children}</div>
    ),
  };
});

describe("EpisodesByTypeChart", () => {
  it("shows empty message when no data", () => {
    render(<EpisodesByTypeChart data={[]} />);
    expect(screen.getByText(/No referral pathway data available/)).toBeInTheDocument();
  });

  it("renders chart container when data is provided", () => {
    const data = [
      { condition_type: "Lung", status: "active", count: 5 },
      { condition_type: "Lung", status: "closed", count: 3 },
      { condition_type: "Breast", status: "active", count: 2 },
    ];
    render(<EpisodesByTypeChart data={data} />);
    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
  });
});
