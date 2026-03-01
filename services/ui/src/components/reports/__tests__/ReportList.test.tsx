import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportList } from "../ReportList";

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockGetMeasureReports = jest.fn();
const mockDeleteMeasureReport = jest.fn();
jest.mock("@/lib/api/measureReports", () => ({
  getMeasureReports: (...args: unknown[]) => mockGetMeasureReports(...args),
  deleteMeasureReport: (...args: unknown[]) => mockDeleteMeasureReport(...args),
}));

function makeReport(overrides: Partial<{ id: string; measure: string; status: string; period: { start: string; end: string }; date: string }> = {}) {
  return {
    id: "R1",
    measure: "Measure/M1",
    status: "complete",
    period: { start: "2024-01-01", end: "2024-01-31" },
    date: "2024-02-01",
    resourceType: "MeasureReport",
    ...overrides,
  };
}

describe("ReportList", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockGetMeasureReports.mockClear();
    mockDeleteMeasureReport.mockClear();
  });

  it("renders Reports title and Create Report button", async () => {
    mockGetMeasureReports.mockResolvedValue({ entry: [] });
    render(<ReportList />);
    await waitFor(() => {
      expect(screen.getByText("Reports")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Create Report/i })).toBeInTheDocument();
  });

  it("shows loading state initially", () => {
    mockGetMeasureReports.mockImplementation(() => new Promise(() => {}));
    render(<ReportList />);
    expect(document.querySelector(".MuiCircularProgress-root")).toBeInTheDocument();
  });

  it("shows empty state when no reports", async () => {
    mockGetMeasureReports.mockResolvedValue({ entry: [] });
    render(<ReportList />);
    await waitFor(() => {
      expect(screen.getByText("No reports found")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Create your first report/i })).toBeInTheDocument();
  });

  it("displays reports in table when loaded", async () => {
    const reports = [
      makeReport({ id: "R1", measure: "Measure/M1", status: "complete" }),
      makeReport({ id: "R2", measure: "Measure/M2", status: "pending" }),
    ];
    mockGetMeasureReports.mockResolvedValue({
      entry: reports.map((r) => ({ resource: r })),
    });
    render(<ReportList />);
    await waitFor(() => {
      expect(screen.getByText("R1")).toBeInTheDocument();
    });
    expect(screen.getByText("R2")).toBeInTheDocument();
    expect(screen.getByText("M1")).toBeInTheDocument();
    expect(screen.getByText("M2")).toBeInTheDocument();
  });

  it("Delete selected button is disabled when no reports selected", async () => {
    mockGetMeasureReports.mockResolvedValue({
      entry: [{ resource: makeReport() }],
    });
    render(<ReportList />);
    await waitFor(() => {
      expect(screen.getByText("R1")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Delete selected/i })).toBeDisabled();
  });

  it("Create Report button navigates to new report page", async () => {
    mockGetMeasureReports.mockResolvedValue({ entry: [] });
    render(<ReportList />);
    await waitFor(() => {
      expect(screen.getByText("No reports found")).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("button", { name: /Create your first report/i }));
    expect(mockPush).toHaveBeenCalledWith("/reports/new/edit");
  });

  it("opens delete dialog when Delete is clicked from row menu", async () => {
    mockGetMeasureReports.mockResolvedValue({
      entry: [{ resource: makeReport({ id: "R1" }) }],
    });
    render(<ReportList />);
    await waitFor(() => {
      expect(screen.getByText("R1")).toBeInTheDocument();
    });
    const table = screen.getByRole("table");
    const dataRow = within(table).getAllByRole("row")[1];
    const menuBtn = within(dataRow).getByRole("button");
    await userEvent.click(menuBtn);
    await userEvent.click(screen.getByText("Delete"));
    expect(screen.getByText(/Are you sure you want to delete report "R1"/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("calls deleteMeasureReport when confirming single delete", async () => {
    mockGetMeasureReports.mockResolvedValue({
      entry: [{ resource: makeReport({ id: "R1" }) }],
    });
    mockDeleteMeasureReport.mockResolvedValue(undefined);
    render(<ReportList />);
    await waitFor(() => {
      expect(screen.getByText("R1")).toBeInTheDocument();
    });
    const table = screen.getByRole("table");
    const dataRow = within(table).getAllByRole("row")[1];
    await userEvent.click(within(dataRow).getByRole("button"));
    await userEvent.click(screen.getByText("Delete"));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(mockDeleteMeasureReport).toHaveBeenCalledWith("R1");
  });
});
