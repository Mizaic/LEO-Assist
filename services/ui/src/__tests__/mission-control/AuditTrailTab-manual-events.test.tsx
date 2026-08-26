/**
 * VT for DI-3A19BE12 -- AuditTrailTab surfaces EpisodeManual* events.
 *
 * Regression for the user-reported bug "Also the audit trial has not
 * tracked what the user did manually": before this fix the tab only
 * fetched PipelineRun events. Now it also fetches the manual
 * EpisodeManualAttach / Detach / Replace / Edit family from
 * /mission-control/patients/{id}/manual-events and renders them in a
 * dedicated "Human edits" section.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import AuditTrailTab from "@/components/mission-control/AuditTrailTab";
import type { MissionEpisode } from "@/lib/missionControlApi";

jest.mock("@/lib/missionControlApi", () => ({
  __esModule: true,
  fetchPatientPipelineEvents: jest.fn(),
  fetchPatientManualEvents: jest.fn(),
}));

import {
  fetchPatientPipelineEvents,
  fetchPatientManualEvents,
} from "@/lib/missionControlApi";

const mockedPipeline = fetchPatientPipelineEvents as jest.MockedFunction<
  typeof fetchPatientPipelineEvents
>;
const mockedManual = fetchPatientManualEvents as jest.MockedFunction<
  typeof fetchPatientManualEvents
>;

const EPISODE: MissionEpisode = {
  episode_id: "ep-001",
  cancer_type: "breast",
  condition_type: "cancer",
  status: "active",
  cancer_stage: null,
  referral_date: "2025-08-12",
  end_date: null,
  diagnostic_interval_days: null,
  benign_interval_days: null,
  primary_care_interval_days: null,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  audit_notes: null,
  audit_flag: false,
  milestones: [],
};

beforeEach(() => {
  jest.clearAllMocks();
  mockedPipeline.mockResolvedValue({
    patient_id: "P-1",
    episode_id: "ep-001",
    events: [],
  });
});

describe("AuditTrailTab -- Human edits section", () => {
  test("renders an empty-state when no manual events exist", async () => {
    mockedManual.mockResolvedValue({
      patient_id: "P-1",
      episode_id: "ep-001",
      events: [],
    });

    render(<AuditTrailTab patientId="P-1" episode={EPISODE} />);

    await waitFor(() => {
      expect(
        screen.getByText(/No manual edits recorded for this pathway yet/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("Human edits")).toBeInTheDocument();
  });

  test("renders an attach event with actor, label and notes", async () => {
    mockedManual.mockResolvedValue({
      patient_id: "P-1",
      episode_id: "ep-001",
      events: [
        {
          id: "ae-1",
          event_type: "EpisodeManualAttach",
          subtype: "episode_manual_edit",
          created_at: "2026-04-22T09:00:00",
          actor_email: "rob@example.com",
          actor_role: "regulatory_reviewer",
          episode_id: "ep-001",
          patient_id: "P-1",
          notes:
            "Attached encounter=enc-1 as milestone=diagnosis_confirmed; status active -> completed",
          before_json: null,
          after_json: null,
        },
      ],
    });

    render(<AuditTrailTab patientId="P-1" episode={EPISODE} />);

    await waitFor(() => {
      expect(screen.getByText("Attached encounter")).toBeInTheDocument();
    });
    expect(screen.getByText(/rob@example.com \(regulatory_reviewer\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/status active -> completed/),
    ).toBeInTheDocument();
  });

  test("renders a delete event with the destructive 'error' chip", async () => {
    mockedManual.mockResolvedValue({
      patient_id: "P-1",
      episode_id: "ep-001",
      events: [
        {
          id: "ae-2",
          event_type: "EpisodeManualDelete",
          subtype: "episode_manual_edit",
          created_at: "2026-04-22T10:00:00",
          actor_email: "rob@example.com",
          actor_role: "administrator",
          episode_id: "ep-001",
          patient_id: "P-1",
          notes: "Deleted episode ep-001 (hard delete with detach)",
          before_json: null,
          after_json: null,
        },
      ],
    });

    render(<AuditTrailTab patientId="P-1" episode={EPISODE} />);

    await waitFor(() => {
      expect(screen.getByText("Deleted pathway")).toBeInTheDocument();
    });
  });

  test("renders newest manual event first", async () => {
    mockedManual.mockResolvedValue({
      patient_id: "P-1",
      episode_id: "ep-001",
      events: [
        {
          id: "ae-old",
          event_type: "EpisodeManualAttach",
          subtype: "episode_manual_edit",
          created_at: "2026-04-21T08:00:00",
          actor_email: "old@example.com",
          actor_role: "triage_clinician",
          episode_id: "ep-001",
          patient_id: "P-1",
          notes: "Old change",
          before_json: null,
          after_json: null,
        },
        {
          id: "ae-new",
          event_type: "EpisodeManualDetach",
          subtype: "episode_manual_edit",
          created_at: "2026-04-22T09:00:00",
          actor_email: "new@example.com",
          actor_role: "regulatory_reviewer",
          episode_id: "ep-001",
          patient_id: "P-1",
          notes: "Recent change",
          before_json: null,
          after_json: null,
        },
      ],
    });

    render(<AuditTrailTab patientId="P-1" episode={EPISODE} />);

    const rows = await screen.findAllByTestId("manual-event-row");
    expect(rows).toHaveLength(2);
    // sortByIsoDateDesc puts the most recent event first.
    expect(rows[0]).toHaveTextContent("Detached encounter");
    expect(rows[0]).toHaveTextContent("Recent change");
    expect(rows[1]).toHaveTextContent("Attached encounter");
    expect(rows[1]).toHaveTextContent("Old change");
  });

  test("a manual-events fetch failure does not hide the pipeline runs section", async () => {
    mockedManual.mockRejectedValue(new Error("Network down"));

    render(<AuditTrailTab patientId="P-1" episode={EPISODE} />);

    await waitFor(() => {
      expect(screen.getByText(/Network down/)).toBeInTheDocument();
    });
    // Pipeline runs section is still rendered.
    expect(screen.getByText("Pipeline runs")).toBeInTheDocument();
  });
});
