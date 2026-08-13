/** Plain-English Validation Lab pipeline stage errors. */

import {
  eventsFromSpans,
  type LabTraceSpan,
} from "../app/admin/validation-lab/inspectorTypes";
import {
  plainEnglishPipelineMessage,
  summarizeStageErrors,
  summarizeStageMessages,
} from "../app/admin/validation-lab/pipelineStageErrors";

describe("plainEnglishPipelineMessage", () => {
  it("explains terminology low confidence in plain English", () => {
    const raw =
      'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- "dysphagia" (score 0.42)';
    const text = plainEnglishPipelineMessage(raw);
    expect(text).toContain("dysphagia");
    expect(text).toContain("55%");
    expect(text).toContain("42%");
    expect(text).toContain("left uncoded");
    expect(text).not.toContain("stopped");
  });

  it("uses plain language when no SNOMED match was found", () => {
    const raw =
      'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- "suspected cancer pathway for assessment of oesophageal cancer" (score 0.00)';
    const text = plainEnglishPipelineMessage(raw);
    expect(text).toContain("no SNOMED match found");
    expect(text).not.toContain("(0% match)");
  });

  it("explains coding verifier not_codeable in plain English", () => {
    const text = plainEnglishPipelineMessage(
      "coding_verifier: 1 entity classified not_codeable",
    );
    expect(text).toContain("not coded");
    expect(text).toContain("descriptor");
  });

  it("explains terminology service outages", () => {
    const text = plainEnglishPipelineMessage("terminology: Connection refused");
    expect(text.toLowerCase()).toContain("terminology service");
  });

  it("strips SBAR stage prefixes from draft assessment errors", () => {
    const text = plainEnglishPipelineMessage(
      "situation:timeout:The AI service took too long to write the Situation section.",
    );
    expect(text).toContain("too long");
    expect(text).not.toMatch(/^situation:/);
  });
});

describe("eventsFromSpans", () => {
  it("includes plain English warning on completed terminology span", () => {
    const warningRaw =
      'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- "dysphagia" (score 0.42)';
    const spans: LabTraceSpan[] = [
      {
        step_id: "act-ref-terminology",
        status: "completed",
        started_at: "2026-08-07T13:52:10.498Z",
        completed_at: "2026-08-07T13:52:11.067Z",
        warnings: [warningRaw],
        warning_summary: summarizeStageMessages([warningRaw]),
      },
    ];
    const events = eventsFromSpans(spans);
    const completed = events.find((ev) => ev.type === "durable_step_completed");
    expect(completed).toBeDefined();
    expect(String(completed?.payload.warning || "")).toContain("dysphagia");
    expect(String(completed?.payload.warning || "")).not.toContain(
      "terminology_low_confidence",
    );
  });

  it("includes plain English error on failed terminology service span", () => {
    const spans: LabTraceSpan[] = [
      {
        step_id: "act-ref-terminology",
        status: "failed",
        started_at: "2026-08-07T13:52:10.498Z",
        completed_at: "2026-08-07T13:52:11.067Z",
        errors: ["terminology: Connection refused"],
        error_summary: summarizeStageErrors(["terminology: Connection refused"]),
      },
    ];
    const events = eventsFromSpans(spans);
    const failed = events.find((ev) => ev.type === "durable_step_failed");
    expect(failed).toBeDefined();
    expect(String(failed?.payload.error || "")).toContain("terminology service");
  });
});
