/** Unit tests for Validation Lab inspector merge layer. */

import {
  mergeInspectorState,
  traceEventFromPayload,
  type LabRunInspectorSnapshot,
} from "../app/admin/validation-lab/inspectorTypes";
import { taskRowsFromSheet } from "../app/admin/validation-lab/RunSheetTasks";

describe("mergeInspectorState", () => {
  it("prefers completed neo4j span over sse running", () => {
    const snapshot: LabRunInspectorSnapshot = {
      lab_run_id: "run-1",
      pipeline_run_id: "run-1",
      lab_status: "running",
      pipeline_status: "running",
      plan_id: "pd-referral-assessment",
      spans: [
        {
          step_id: "act-ref-extract",
          status: "completed",
          source: "neo4j",
        },
      ],
      sse_path: "/api/pipeline/progress/run-1",
    };
    const events = [
      traceEventFromPayload({
        type: "durable_step_started",
        action_id: "act-ref-extract",
        status: "running",
        ts: "2026-08-06T10:00:01Z",
      }),
    ];
    const merged = mergeInspectorState(snapshot, events, []);
    expect(merged.spans[0].status).toBe("completed");
  });

  it("creates in-flight span from sse before neo4j row exists", () => {
    const merged = mergeInspectorState(
      null,
      [
        traceEventFromPayload({
          type: "durable_step_started",
          action_id: "act-ref-extract",
          status: "running",
          ts: "2026-08-06T10:00:01Z",
        }),
      ],
      [],
    );
    expect(merged.spans).toHaveLength(1);
    expect(merged.spans[0].step_id).toBe("act-ref-extract");
    expect(merged.spans[0].status).toBe("running");
  });

  it("hydrates log events from neo4j spans when sse is empty", () => {
    const snapshot: LabRunInspectorSnapshot = {
      lab_run_id: "lab-1",
      pipeline_run_id: "pipe-1",
      lab_status: "completed",
      pipeline_status: "completed",
      plan_id: "pd-referral-assessment",
      spans: [
        {
          step_id: "act-ref-extract",
          status: "completed",
          started_at: "2026-08-06T10:00:00Z",
          completed_at: "2026-08-06T10:00:05Z",
          source: "neo4j",
        },
      ],
      sse_path: "/api/pipeline/progress/pipe-1",
    };
    const merged = mergeInspectorState(snapshot, [], []);
    expect(merged.events.length).toBeGreaterThanOrEqual(2);
    expect(merged.events[0].type).toBe("durable_step_started");
  });
});

describe("taskRowsFromSheet liveSpans fallback", () => {
  it("uses liveSpans when stage_progress is empty", () => {
    const rows = taskRowsFromSheet({
      phases: [
        { phase_id: "extraction", status: "queued" },
        { phase_id: "verification", status: "queued" },
      ],
      terminal: false,
      status: "running",
      liveSpans: [
        {
          step_id: "act-ref-extract",
          status: "running",
          worker_id: "worker-a",
        },
      ],
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].key).toBe("act-ref-extract");
    expect(rows[0].status).toBe("running");
  });
});
