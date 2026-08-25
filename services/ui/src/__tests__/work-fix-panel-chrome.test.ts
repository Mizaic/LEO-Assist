/**
 * VT-CE7006EE / DI-6BD7B681 -- My work engineer panel uses Knowledge
 * draft, review, and two-person publish. Static-source VT.
 */
import { readFileSync } from "fs";
import { join } from "path";

const PANEL = readFileSync(
  join(__dirname, "../app/work/WorkFixPanel.tsx"),
  "utf8",
);
const PANES = readFileSync(
  join(__dirname, "../app/work/EngineerPanes.tsx"),
  "utf8",
);
const API = readFileSync(join(__dirname, "../app/work/workFixApi.ts"), "utf8");
const REVIEW = readFileSync(
  join(__dirname, "../app/work/WorkReviewCardDialog.tsx"),
  "utf8",
);
const EXTRACT = readFileSync(
  join(__dirname, "../components/operations/ExtractionQualityReviewDialog.tsx"),
  "utf8",
);
const SOURCE = PANEL + PANES;

describe("Engineer panel -- in-context Knowledge (DI-6BD7B681)", () => {
  it("names the engineer panel and the four Knowledge steps", () => {
    expect(PANEL).toContain("data-testid=\"work-fix-panel\"");
    expect(SOURCE).toContain("Engineer panel");
    expect(SOURCE).toContain("Debug");
    expect(SOURCE).toContain("Fix");
    expect(SOURCE).toContain("Submit for review");
    expect(SOURCE).toContain("Deploy");
  });

  it("drafts a mapping or exclude and does not write live coding on save", () => {
    expect(API).toContain("savePhraseDraft");
    expect(API).toContain("submitPhrase");
    expect(API).toContain("publishPhrase");
    expect(API).not.toContain("upsertSurfaceFormMapping");
    expect(API).not.toContain("post-processor-rules");
  });

  it("does not send the user to Knowledge to make the fix", () => {
    expect(PANEL).not.toContain("/admin/knowledge");
    expect(PANEL).not.toContain("router.push");
  });

  it("sits inside the coding and extraction work windows", () => {
    expect(REVIEW).toContain("WorkFixPanel");
    expect(EXTRACT).toContain("WorkFixPanel");
  });

  it("can save a missed word and its sentence as a teaching example", () => {
    expect(PANES).toContain("Teach the extractor");
    expect(API).toContain("saveTeachExample");
    expect(API).toContain("extraction-reviews/few-shot");
    expect(API).not.toContain("/admin/prompts");
  });

  it("works with language model and named-entity recognition extractions", () => {
    expect(API).toContain("extracted_source");
    expect(PANES).toContain("language model (LLM)");
    expect(PANES).toContain("named-entity recognition (NER)");
    expect(EXTRACT).toContain("extractionSource");
  });
});
