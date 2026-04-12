import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import EncounterMissionControl from "@/components/mission-control/EncounterMissionControl";

jest.mock("@/context/OrgContext", () => ({
  useOrgId: () => "org-1",
}));

const fetchEncounterList = jest.fn();
const fetchEncounterKPIs = jest.fn();
const batchResetAndRecodeEncounters = jest.fn();

jest.mock("@/lib/missionControlApi", () => ({
  fetchEncounterList: (...args: unknown[]) => fetchEncounterList(...args),
  fetchEncounterKPIs: (...args: unknown[]) => fetchEncounterKPIs(...args),
  batchResetAndRecodeEncounters: (...args: unknown[]) =>
    batchResetAndRecodeEncounters(...args),
}));

describe("EncounterMissionControl", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  beforeEach(() => {
    jest.spyOn(window, "confirm").mockReturnValue(true);
    fetchEncounterList.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 25,
      items: [
        {
          encounter_id: "enc-1",
          patient_id: "p-1",
          encounter_date: "2025-01-01",
          text: "Patient has cough",
          coded_count: 1,
          match_type: "hybrid",
        },
      ],
    });
    fetchEncounterKPIs.mockResolvedValue({
      total_encounters: 10,
      total_patients: 8,
      coded_encounters: 4,
      median_codes_per_encounter: 1.2,
    });
    batchResetAndRecodeEncounters.mockResolvedValue({
      batch_id: "b-1",
      requested: 1,
      queued_count: 1,
      failed_count: 0,
      dry_run: false,
      trigger_analysis: false,
      queued: [{ patient_id: "p-1", encounter_id: "enc-1", run_id: "r-1", stream_path: "/api/pipeline/progress/r-1" }],
      failed: [],
    });
    (global as unknown as { EventSource: unknown }).EventSource = class {
      addEventListener() {}
      close() {}
    };
  });

  test("loads and renders encounter row", async () => {
    render(<EncounterMissionControl />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(fetchEncounterList).toHaveBeenCalled());
    expect(await screen.findByText("p-1")).toBeInTheDocument();
    expect(screen.getByText("hybrid")).toBeInTheDocument();
  });

  test("shortlist then batch submit uses selected encounters", async () => {
    render(<EncounterMissionControl />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("p-1");

    const switches = screen.getAllByRole("switch");
    fireEvent.click(switches[switches.length - 1]);
    fireEvent.click(
      screen.getByRole("button", { name: /Reset \+ recode selected/ })
    );

    await waitFor(() => expect(batchResetAndRecodeEncounters).toHaveBeenCalled());
    expect(batchResetAndRecodeEncounters).toHaveBeenCalledWith(
      [{ patient_id: "p-1", encounter_id: "enc-1" }],
      false,
      undefined
    );
  });

  test("submit all results queues across loaded search pages", async () => {
    fetchEncounterList
      .mockResolvedValueOnce({
        total: 2,
        page: 1,
        page_size: 100,
        items: [
          {
            encounter_id: "enc-1",
            patient_id: "p-1",
            encounter_date: "2025-01-01",
            text: "Patient has cough",
            coded_count: 1,
            match_type: "hybrid",
          },
        ],
      })
      .mockResolvedValueOnce({
        total: 2,
        page: 1,
        page_size: 100,
        items: [
          {
            encounter_id: "enc-1",
            patient_id: "p-1",
            encounter_date: "2025-01-01",
            text: "Patient has cough",
            coded_count: 1,
            match_type: "hybrid",
          },
          {
            encounter_id: "enc-2",
            patient_id: "p-2",
            encounter_date: "2025-01-02",
            text: "Patient has rash",
            coded_count: 0,
            match_type: "keyword",
          },
        ],
      });
    batchResetAndRecodeEncounters.mockResolvedValueOnce({
      batch_id: "b-all",
      requested: 2,
      queued_count: 2,
      failed_count: 0,
      dry_run: false,
      trigger_analysis: false,
      queued: [
        { patient_id: "p-1", encounter_id: "enc-1", run_id: "r-1", stream_path: "/api/pipeline/progress/r-1" },
        { patient_id: "p-2", encounter_id: "enc-2", run_id: "r-2", stream_path: "/api/pipeline/progress/r-2" },
      ],
      failed: [],
    });

    render(<EncounterMissionControl />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("p-1");

    fireEvent.click(screen.getByRole("button", { name: /Reset \+ recode all results/ }));

    await waitFor(() => expect(batchResetAndRecodeEncounters).toHaveBeenCalled());
    expect(batchResetAndRecodeEncounters).toHaveBeenCalledWith(
      [
        { patient_id: "p-1", encounter_id: "enc-1" },
        { patient_id: "p-2", encounter_id: "enc-2" },
      ],
      false,
      undefined
    );
  });
});
