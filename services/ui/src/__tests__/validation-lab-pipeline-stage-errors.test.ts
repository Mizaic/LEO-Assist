/** Plain-English Validation Lab pipeline stage errors. */

import {
  eventsFromSpans,
  type LabTraceSpan,
} from "../app/admin/validation-lab/inspectorTypes";
import {
  plainEnglishPipelineError,
  summarizeStageErrors,
} from "../app/admin/validation-lab/pipelineStageErrors";

describe("plainEnglishPipelineError", () => {
  it("explains terminology low confidence in plain English", () => {
    const raw =
      'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- "dysphagia" (score 0.42)';
    const text = plainEnglishPipelineError(raw);
    expect(text).toContain("dysphagia");
    expect(text).toContain("55%");
    expect(text).toContain("42%");
    expect(text).toContain("unsafe codes");
  });

  it("explains terminology service outages", () => {
    const text = plainEnglishPipelineError("terminology: Connection refused");
    expect(text.toLowerCase()).toContain("terminology service");
  });
});

describe("eventsFromSpans", () => {
  it("includes plain English error on failed terminology span", () => {
    const spans: LabTraceSpan[] = [
      {
        step_id: "act-ref-terminology",
        status: "failed",
        started_at: "2026-08-07T13:52:10.498Z",
        completed_at: "2026-08-07T13:52:11.067Z",
        errors: [
          'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- "dysphagia" (score 0.42)',
        ],
        error_summary: summarizeStageErrors([
          'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- "dysphagia" (score 0.42)',
        ]),
      },
    ];
    const events = eventsFromSpans(spans);
    const failed = events.find((ev) => ev.type === "durable_step_failed");
    expect(failed).toBeDefined();
    expect(String(failed?.payload.error || "")).toContain("dysphagia");
    expect(String(failed?.payload.error || "")).not.toContain(
      "terminology_low_confidence",
    );
  });
});
