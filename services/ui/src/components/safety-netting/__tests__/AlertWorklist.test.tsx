import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AlertWorklist from "../AlertWorklist";
import type { SafetyNetAlert } from "@/lib/analyticsApi";

function makeAlert(overrides: Partial<SafetyNetAlert> = {}): SafetyNetAlert {
  return {
    id: "A1",
    type: "missing_safety_netting",
    severity: "high",
    description: "No follow-up documented",
    patient_id: "P001",
    ...overrides,
  };
}

describe("AlertWorklist", () => {
  it("shows empty state when no alerts", () => {
    render(
      <AlertWorklist alerts={[]} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText(/No alerts match your filters/)).toBeInTheDocument();
  });

  it("renders table headers", () => {
    const alerts = [makeAlert()];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText("Severity")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getByText("Cancer type")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("renders patient group header with patient ID", () => {
    const alerts = [makeAlert({ patient_id: "P001" })];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText("P001")).toBeInTheDocument();
  });

  it("shows alert count in patient group header", () => {
    const alerts = [
      makeAlert({ id: "A1", patient_id: "P001" }),
      makeAlert({ id: "A2", patient_id: "P001" }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText("2 alerts")).toBeInTheDocument();
  });

  it("shows singular 'alert' for single alert", () => {
    const alerts = [makeAlert({ id: "A1", patient_id: "P001" })];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText("1 alert")).toBeInTheDocument();
  });

  it("groups alerts by patient", () => {
    const alerts = [
      makeAlert({ id: "A1", patient_id: "P001", type: "type_A" }),
      makeAlert({ id: "A2", patient_id: "P002", type: "type_B" }),
      makeAlert({ id: "A3", patient_id: "P001", type: "type_C" }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText("P001")).toBeInTheDocument();
    expect(screen.getByText("P002")).toBeInTheDocument();
    expect(screen.getByText("2 alerts")).toBeInTheDocument();
    expect(screen.getByText("1 alert")).toBeInTheDocument();
  });

  it("renders alert rows with data", () => {
    const alerts = [
      makeAlert({
        id: "A1",
        severity: "critical",
        type: "investigation_gap",
        description: "No investigation after referral",
        patient_id: "P001",
        condition_type: "Lung",
      }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("investigation_gap")).toBeInTheDocument();
    expect(screen.getByText("No investigation after referral")).toBeInTheDocument();
    expect(screen.getByText("Lung")).toBeInTheDocument();
  });

  it("shows check icon for actioned alerts", () => {
    const alerts = [makeAlert({ actioned: true })];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByLabelText("actioned")).toBeInTheDocument();
  });

  it("does not show check icon for un-actioned alerts", () => {
    const alerts = [makeAlert({ actioned: false })];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.queryByLabelText("actioned")).not.toBeInTheDocument();
  });

  it("calls onSelect when an alert row is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = jest.fn();
    const alerts = [makeAlert({ id: "A1", type: "investigation_gap" })];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={onSelect} />,
    );
    await user.click(screen.getByText("investigation_gap"));
    expect(onSelect).toHaveBeenCalledWith(alerts[0]);
  });

  it("collapses a patient group when header is clicked", async () => {
    const user = userEvent.setup();
    const alerts = [
      makeAlert({ id: "A1", patient_id: "P001", type: "type_A" }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText("type_A")).toBeInTheDocument();
    await user.click(screen.getByText("P001"));
    expect(screen.queryByText("type_A")).not.toBeInTheDocument();
  });

  it("expands a collapsed patient group when header is clicked again", async () => {
    const user = userEvent.setup();
    const alerts = [
      makeAlert({ id: "A1", patient_id: "P001", type: "type_A" }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    await user.click(screen.getByText("P001"));
    expect(screen.queryByText("type_A")).not.toBeInTheDocument();
    await user.click(screen.getByText("P001"));
    expect(screen.getByText("type_A")).toBeInTheDocument();
  });

  it("collapse all / expand all via header button", async () => {
    const user = userEvent.setup();
    const alerts = [
      makeAlert({ id: "A1", patient_id: "P001", type: "type_A" }),
      makeAlert({ id: "A2", patient_id: "P002", type: "type_B" }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText("type_A")).toBeInTheDocument();
    expect(screen.getByText("type_B")).toBeInTheDocument();

    await user.click(screen.getByLabelText("collapse all patients"));
    expect(screen.queryByText("type_A")).not.toBeInTheDocument();
    expect(screen.queryByText("type_B")).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("expand all patients"));
    expect(screen.getByText("type_A")).toBeInTheDocument();
    expect(screen.getByText("type_B")).toBeInTheDocument();
  });

  it("shows outstanding count in group header", () => {
    const alerts = [
      makeAlert({ id: "A1", patient_id: "P001", actioned: false }),
      makeAlert({ id: "A2", patient_id: "P001", actioned: true }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    expect(screen.getByText("1 outstanding")).toBeInTheDocument();
  });

  it("sorts patient groups by worst severity", () => {
    const alerts = [
      makeAlert({ id: "A1", patient_id: "P-low", severity: "low", type: "low_type" }),
      makeAlert({ id: "A2", patient_id: "P-crit", severity: "critical", type: "crit_type" }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} />,
    );
    const rows = screen.getAllByRole("row");
    const headerIdx = rows.findIndex((r) => r.textContent?.includes("P-crit"));
    const lowIdx = rows.findIndex((r) => r.textContent?.includes("P-low"));
    expect(headerIdx).toBeLessThan(lowIdx);
  });
});

describe("AlertWorklist flat mode", () => {
  it("shows empty state when no alerts", () => {
    render(
      <AlertWorklist alerts={[]} selectedId={null} onSelect={jest.fn()} viewMode="flat" />,
    );
    expect(screen.getByText(/No alerts match your filters/)).toBeInTheDocument();
  });

  it("renders flat table headers including Patient column", () => {
    const alerts = [makeAlert()];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} viewMode="flat" />,
    );
    expect(screen.getByText("Severity")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getByText("Patient")).toBeInTheDocument();
    expect(screen.getByText("Cancer type")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("does not render patient group headers in flat mode", () => {
    const alerts = [
      makeAlert({ id: "A1", patient_id: "P001", type: "type_A" }),
      makeAlert({ id: "A2", patient_id: "P002", type: "type_B" }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} viewMode="flat" />,
    );
    expect(screen.queryByLabelText(/collapse all/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/expand all/)).not.toBeInTheDocument();
  });

  it("renders all alert rows in a flat list", () => {
    const alerts = [
      makeAlert({ id: "A1", patient_id: "P001", type: "type_A" }),
      makeAlert({ id: "A2", patient_id: "P002", type: "type_B" }),
      makeAlert({ id: "A3", patient_id: "P001", type: "type_C" }),
    ];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} viewMode="flat" />,
    );
    expect(screen.getByText("type_A")).toBeInTheDocument();
    expect(screen.getByText("type_B")).toBeInTheDocument();
    expect(screen.getByText("type_C")).toBeInTheDocument();
    expect(screen.getAllByText("P001")).toHaveLength(2);
    expect(screen.getByText("P002")).toBeInTheDocument();
  });

  it("calls onSelect when a flat row is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = jest.fn();
    const alerts = [makeAlert({ id: "A1", type: "investigation_gap" })];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={onSelect} viewMode="flat" />,
    );
    await user.click(screen.getByText("investigation_gap"));
    expect(onSelect).toHaveBeenCalledWith(alerts[0]);
  });

  it("shows dashes for missing patient_id and condition_type in flat mode", () => {
    const alerts = [makeAlert({ patient_id: undefined, condition_type: undefined })];
    render(
      <AlertWorklist alerts={alerts} selectedId={null} onSelect={jest.fn()} viewMode="flat" />,
    );
    const dashes = screen.getAllByText("-");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });
});
