import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AlertFilters from "../AlertFilters";
import type { AlertFilterState } from "../AlertFilters";
import type { SafetyNetAlert } from "@/lib/analyticsApi";

function makeAlert(overrides: Partial<SafetyNetAlert> = {}): SafetyNetAlert {
  return {
    id: "A1",
    type: "missing_safety_netting",
    severity: "high",
    description: "No follow-up documented",
    ...overrides,
  };
}

const BASE_FILTERS: AlertFilterState = {
  search: "",
  severity: null,
  type: null,
  actionedFilter: "all",
};

const defaultProps = {
  filters: BASE_FILTERS,
  onChange: jest.fn(),
  alerts: [] as SafetyNetAlert[],
  viewMode: "grouped" as const,
  onViewModeChange: jest.fn(),
};

describe("AlertFilters", () => {
  it("renders search input", () => {
    render(<AlertFilters {...defaultProps} />);
    expect(
      screen.getByPlaceholderText(/Search by patient/),
    ).toBeInTheDocument();
  });

  it("renders severity chips with counts", () => {
    const alerts = [
      makeAlert({ id: "A1", severity: "high" }),
      makeAlert({ id: "A2", severity: "high" }),
      makeAlert({ id: "A3", severity: "medium" }),
    ];
    render(<AlertFilters {...defaultProps} alerts={alerts} />);
    expect(screen.getByText("high (2)")).toBeInTheDocument();
    expect(screen.getByText("medium (1)")).toBeInTheDocument();
  });

  it("does not render severity chips with zero count", () => {
    const alerts = [makeAlert({ severity: "high" })];
    render(<AlertFilters {...defaultProps} alerts={alerts} />);
    expect(screen.queryByText(/critical/)).not.toBeInTheDocument();
    expect(screen.queryByText(/low/)).not.toBeInTheDocument();
  });

  it("renders type chips with counts", () => {
    const alerts = [
      makeAlert({ id: "A1", type: "investigation_gap" }),
      makeAlert({ id: "A2", type: "investigation_gap" }),
      makeAlert({ id: "A3", type: "excessive_referral_wait" }),
    ];
    render(<AlertFilters {...defaultProps} alerts={alerts} />);
    expect(screen.getByText("investigation_gap (2)")).toBeInTheDocument();
    expect(screen.getByText("excessive_referral_wait (1)")).toBeInTheDocument();
  });

  it("calls onChange with search text", async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();
    render(<AlertFilters {...defaultProps} onChange={onChange} />);
    await user.type(screen.getByPlaceholderText(/Search by patient/), "P001");
    expect(onChange).toHaveBeenCalled();
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.search).toContain("1");
  });

  it("calls onChange with severity toggle", async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();
    const alerts = [makeAlert({ severity: "high" })];
    render(<AlertFilters {...defaultProps} onChange={onChange} alerts={alerts} />);
    await user.click(screen.getByText("high (1)"));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ severity: "high" }),
    );
  });

  it("clears severity when clicking the active severity chip", async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();
    const alerts = [makeAlert({ severity: "high" })];
    const activeFilters = { ...BASE_FILTERS, severity: "high" };
    render(
      <AlertFilters {...defaultProps} filters={activeFilters} onChange={onChange} alerts={alerts} />,
    );
    await user.click(screen.getByText("high (1)"));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ severity: null }),
    );
  });

  it("renders toggle buttons for actioned filter", () => {
    render(<AlertFilters {...defaultProps} />);
    expect(screen.getByText("All")).toBeInTheDocument();
    expect(screen.getByText("Outstanding")).toBeInTheDocument();
    expect(screen.getByText("Actioned")).toBeInTheDocument();
  });

  it("renders view mode toggle with grouped and flat buttons", () => {
    render(<AlertFilters {...defaultProps} />);
    expect(screen.getByLabelText("group by patient")).toBeInTheDocument();
    expect(screen.getByLabelText("flat list")).toBeInTheDocument();
  });

  it("calls onViewModeChange when flat is clicked", async () => {
    const user = userEvent.setup();
    const onViewModeChange = jest.fn();
    render(
      <AlertFilters {...defaultProps} viewMode="grouped" onViewModeChange={onViewModeChange} />,
    );
    await user.click(screen.getByLabelText("flat list"));
    expect(onViewModeChange).toHaveBeenCalledWith("flat");
  });

  it("calls onViewModeChange when grouped is clicked", async () => {
    const user = userEvent.setup();
    const onViewModeChange = jest.fn();
    render(
      <AlertFilters {...defaultProps} viewMode="flat" onViewModeChange={onViewModeChange} />,
    );
    await user.click(screen.getByLabelText("group by patient"));
    expect(onViewModeChange).toHaveBeenCalledWith("grouped");
  });
});
