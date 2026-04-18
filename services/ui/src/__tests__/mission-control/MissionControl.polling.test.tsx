import React from "react";
import { act, render, waitFor } from "@testing-library/react";
import MissionControl from "@/components/mission-control/MissionControl";
import {
  fetchMissionKPIs,
  fetchMissionPatients,
  fetchPatientRebuildStatus,
} from "@/lib/missionControlApi";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
}));

jest.mock("@/context/OrgContext", () => ({
  useOrgId: () => "org-1",
}));

jest.mock("@/context/AnalyticsDateFilterContext", () => ({
  useAnalyticsDateFilter: () => ({
    dateFrom: "",
    dateTo: "",
    appliedFrom: "",
    appliedTo: "",
    setDateFrom: jest.fn(),
    setDateTo: jest.fn(),
    apply: jest.fn(),
    clear: jest.fn(),
  }),
}));

jest.mock("@/components/mission-control/CommandBar", () => () => <div>CommandBar</div>);
jest.mock("@/components/mission-control/KPIStrip", () => () => <div>KPIStrip</div>);
jest.mock(
  "@/components/mission-control/PatientCaseTable",
  () =>
    function MockPatientCaseTable() {
      return <div>PatientCaseTable</div>;
    }
);
jest.mock(
  "@/components/mission-control/PatientDetailDrawer",
  () =>
    function MockPatientDetailDrawer() {
      return <div>PatientDetailDrawer</div>;
    }
);

jest.mock("@/lib/missionControlApi", () => ({
  fetchMissionKPIs: jest.fn(),
  fetchMissionPatients: jest.fn(),
  fetchPatientRebuildStatus: jest.fn(),
}));

const mockFetchMissionKPIs = fetchMissionKPIs as jest.MockedFunction<
  typeof fetchMissionKPIs
>;
const mockFetchMissionPatients = fetchMissionPatients as jest.MockedFunction<
  typeof fetchMissionPatients
>;
const mockFetchPatientRebuildStatus =
  fetchPatientRebuildStatus as jest.MockedFunction<typeof fetchPatientRebuildStatus>;

const BASE_KPIS = {
  total_patients: 1,
  confirmed_cancer: 0,
  confirmed_cancer_patients: 0,
  pathway_closures: 0,
  pathway_closure_patients: 0,
  median_diagnostic_interval_days: null,
  safety_netting_rate: 0,
  needs_review_count: 1,
};

const ONE_AWAITING_PATIENT = {
  total: 1,
  page: 1,
  page_size: 25,
  patients: [
    {
      patient_id: "4181221113",
      gender: "female",
      age: 65,
      practice_name: "Practice A",
      episodes: [],
    },
  ],
};

describe("MissionControl rebuild polling", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mockFetchMissionKPIs.mockResolvedValue(BASE_KPIS);
    mockFetchMissionPatients.mockResolvedValue(ONE_AWAITING_PATIENT);
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  test("does not keep polling when rebuild status is idle", async () => {
    mockFetchPatientRebuildStatus.mockResolvedValue({
      patient_id: "4181221113",
      run_id: null,
      status: "idle",
      message: null,
      updated_at: null,
      queued_jobs: null,
      queue_depth: null,
      queue_position_estimate: null,
      median_duration_seconds: null,
      throughput_per_minute: null,
      eta_seconds_estimate: null,
    });

    render(<MissionControl />);

    let initialStatusCalls = 0;
    await waitFor(() => {
      expect(mockFetchPatientRebuildStatus.mock.calls.length).toBeGreaterThanOrEqual(1);
      initialStatusCalls = mockFetchPatientRebuildStatus.mock.calls.length;
    });

    await act(async () => {
      jest.advanceTimersByTime(24000);
    });

    expect(mockFetchPatientRebuildStatus.mock.calls.length).toBe(initialStatusCalls);
  });

  test("refreshes table once queued rebuild completes", async () => {
    mockFetchPatientRebuildStatus
      .mockResolvedValueOnce({
        patient_id: "4181221113",
        run_id: "run-1",
        status: "queued",
        message: "queued",
        updated_at: null,
        queued_jobs: 1,
        queue_depth: 3,
        queue_position_estimate: 2,
        median_duration_seconds: 90,
        throughput_per_minute: 1,
        eta_seconds_estimate: 180,
      })
      .mockResolvedValueOnce({
        patient_id: "4181221113",
        run_id: "run-1",
        status: "queued",
        message: "queued",
        updated_at: null,
        queued_jobs: 1,
        queue_depth: 2,
        queue_position_estimate: 1,
        median_duration_seconds: 90,
        throughput_per_minute: 1,
        eta_seconds_estimate: 120,
      })
      .mockResolvedValue({
        patient_id: "4181221113",
        run_id: "run-1",
        status: "completed",
        message: "done",
        updated_at: null,
        queued_jobs: 0,
        queue_depth: 0,
        queue_position_estimate: 0,
        median_duration_seconds: 90,
        throughput_per_minute: 1,
        eta_seconds_estimate: 0,
      });

    render(<MissionControl />);

    let initialPatientCalls = 0;
    await waitFor(() => {
      expect(mockFetchMissionPatients.mock.calls.length).toBeGreaterThanOrEqual(1);
      expect(mockFetchPatientRebuildStatus.mock.calls.length).toBeGreaterThanOrEqual(1);
      initialPatientCalls = mockFetchMissionPatients.mock.calls.length;
    });

    await act(async () => {
      jest.advanceTimersByTime(8000);
    });

    await waitFor(() => {
      expect(mockFetchMissionPatients.mock.calls.length).toBeGreaterThan(initialPatientCalls);
      expect(mockFetchMissionKPIs.mock.calls.length).toBeGreaterThan(initialPatientCalls);
    });
  });
});
