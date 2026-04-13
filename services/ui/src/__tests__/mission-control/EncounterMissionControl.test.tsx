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
    expect(screen.getByText("Hybrid")).toBeInTheDocument();
  });

  test("shortlist then batch submit uses selected encounters", async () => {
    render(<EncounterMissionControl />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("p-1");

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(
      screen.getByRole("button", { name: /Recode selected/ })
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

    fireEvent.click(screen.getByRole("button", { name: /Recode all results/ }));
    fireEvent.click(screen.getByRole("button", { name: /Recode all 2/ }));

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

  test("large batch uses shared poll fetch instead of per-encounter SSE", async () => {
    // Build 7 encounters (> SSE_CONNECTION_LIMIT of 6) so the hook switches to shared polling.
    const makeEncounter = (n: number) => ({
      encounter_id: `enc-${n}`,
      patient_id: `p-${n}`,
      encounter_date: "2025-01-01",
      text: `Note ${n}`,
      coded_count: 0,
      match_type: "keyword",
    });
    const encounters = Array.from({ length: 7 }, (_, i) => makeEncounter(i + 1));

    fetchEncounterList.mockResolvedValue({
      total: 7,
      page: 1,
      page_size: 100,
      items: encounters,
    });
    batchResetAndRecodeEncounters.mockResolvedValueOnce({
      batch_id: "b-large",
      requested: 7,
      queued_count: 7,
      failed_count: 0,
      dry_run: false,
      trigger_analysis: false,
      queued: encounters.map((e) => ({
        patient_id: e.patient_id,
        encounter_id: e.encounter_id,
        run_id: `r-${e.encounter_id}`,
        stream_path: `/api/pipeline/progress/r-${e.encounter_id}`,
      })),
      failed: [],
    });

    const sseSpy = jest.fn();
    (global as unknown as { EventSource: unknown }).EventSource = class {
      constructor() { sseSpy(); }
      addEventListener() {}
      close() {}
    };
    const fetchSpy = jest.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => encounters.map((e) => ({
        run_id: `r-${e.encounter_id}`,
        state: "completed",
      })),
    } as Response);

    render(<EncounterMissionControl />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("p-1");

    fireEvent.click(screen.getByRole("button", { name: /Recode all results/ }));
    fireEvent.click(screen.getByRole("button", { name: /Recode all 7/ }));

    await waitFor(() => expect(batchResetAndRecodeEncounters).toHaveBeenCalled());

    // SSE must NOT have been opened for any encounter.
    expect(sseSpy).not.toHaveBeenCalled();
    // The batch-status endpoint must have been called via fetch.
    await waitFor(() =>
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining("/api/pipeline/progress-status/batch"),
        expect.objectContaining({ method: "POST" })
      )
    );

    fetchSpy.mockRestore();
  });

  test("Show 3D map chip appears after results load", async () => {
    render(<EncounterMissionControl />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(fetchEncounterList).toHaveBeenCalled());
    expect(await screen.findByText("Show 3D map")).toBeInTheDocument();
  });
});
