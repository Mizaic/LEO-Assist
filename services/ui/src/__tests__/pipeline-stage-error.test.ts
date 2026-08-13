/**
 * Stage-test error copy must never dump an HTML page into the UI.
 */
import { sanitizeStageError } from "../components/workbench/usePipelineStageRunner";

describe("sanitizeStageError", () => {
  it("does not dump HTML from a missing Next.js route", () => {
    const html = "<!DOCTYPE html><html lang=\"en\"><head></head><body>LEO</body></html>";
    expect(sanitizeStageError(html, 404)).toBe(
      "The test service is not available (HTTP 404).",
    );
  });

  it("keeps a short JSON error body", () => {
    expect(sanitizeStageError("rule not found", 404)).toBe("rule not found");
  });
});
