/**
 * VT-LEO-AI-184 -- SBAR Playground page chrome
 *
 * Static-source verification (per the VT-LEO-AI-142 pattern) for the
 * AI Summarisation playground introduced by DI-LEO-AI-194:
 *   - The page is wired into the Knowledge tab registry under
 *     `ai-summarisation`, with stable URL key and copy.
 *   - The playground component carries the test-only banner, fields
 *     for patient id, situation artefacts, background sources, and
 *     guideline ids, plus a submit control.
 *   - The new UI proxy routes exist at
 *     /api/sbar/jobs, /api/sbar/jobs/{runId}/events, and
 *     /api/sbar/assessments/{assessmentId}.
 *
 * A live render of the playground is not attempted here -- the
 * component opens an EventSource on submit and the stream itself is
 * exercised by Playwright in `sbar-playground.spec.ts`.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app");

const FILES = {
  knowledgePage: path.join(ROOT, "admin", "knowledge", "page.tsx"),
  playgroundPage: path.join(ROOT, "admin", "ai-summarisation", "page.tsx"),
  playgroundComponent: path.join(
    ROOT,
    "admin",
    "ai-summarisation",
    "SbarPlayground.tsx",
  ),
  copy: path.resolve(__dirname, "..", "lib", "knowledgeCopy.ts"),
  hook: path.resolve(__dirname, "..", "hooks", "useSbarStream.ts"),
  jobsRoute: path.join(ROOT, "api", "sbar", "jobs", "route.ts"),
  eventsRoute: path.join(
    ROOT,
    "api",
    "sbar",
    "jobs",
    "[runId]",
    "events",
    "route.ts",
  ),
  assessmentRoute: path.join(
    ROOT,
    "api",
    "sbar",
    "assessments",
    "[assessmentId]",
    "route.ts",
  ),
};

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-184 SBAR playground chrome", () => {
  it("registers the ai-summarisation tab", () => {
    const src = read(FILES.knowledgePage);
    expect(src).toMatch(
      /key:\s*"ai-summarisation",\s*label:\s*"AI Summarisation"/,
    );
    expect(src).toMatch(/AiSummarisationPage/);
    expect(src).toMatch(/admin\/ai-summarisation\/page/);
  });

  it("declares ai-summarisation copy with a default block", () => {
    const src = read(FILES.copy);
    expect(src).toMatch(/"ai-summarisation":\s*\{/);
    expect(src).toMatch(/Try out the SBAR summary/);
  });

  it("exposes the SbarPlayground page entry", () => {
    const src = read(FILES.playgroundPage);
    expect(src).toMatch(/import\("\.\/SbarPlayground"\)/);
    expect(src).toMatch(/AiSummarisationPage/);
  });

  it("playground renders the test-only banner and consumes the four shared primitives", () => {
    const src = read(FILES.playgroundComponent);
    for (const id of [
      "sbar-test-only-banner",
      "sbar-pick-patient",
      "sbar-pick-sources",
      "sbar-concern",
      "sbar-submit",
    ]) {
      expect(src).toContain(id);
    }
    expect(src).toMatch(/PatientFinder/);
    expect(src).toMatch(/SummarisationContextSelect/);
    expect(src).toMatch(/BackgroundSourcePicker/);
    expect(src).toMatch(/GuidelinePicker/);
  });

  it("playground surfaces all four SBAR stages", () => {
    const src = read(FILES.playgroundComponent);
    expect(src).toContain("data-testid={`sbar-stage-${stage}`}");
    // STAGE_LABELS / STAGE_THEME live in the shared sbar-final
    // module so other apps can reuse the same palette and copy.
    expect(src).toMatch(/STAGE_LABELS,?\s*\n?\s*STAGE_THEME/);
  });

  it("hook posts to /api/sbar/jobs and subscribes to the events SSE", () => {
    const src = read(FILES.hook);
    expect(src).toContain('"/api/sbar/jobs"');
    expect(src).toMatch(/method:\s*"POST"/);
    expect(src).toContain("`${origin}/api/sbar/jobs/${encodeURIComponent(runId)}/events`");
    expect(src).toContain("/api/sbar/assessments/");
    expect(src).toMatch(/sbar_started/);
    expect(src).toMatch(/sbar_stage_started/);
    expect(src).toMatch(/sbar_stage_completed/);
    expect(src).toMatch(/sbar_completed/);
  });

  it("UI proxy: /api/sbar/jobs forwards POST to the Core API", () => {
    const src = read(FILES.jobsRoute);
    expect(src).toMatch(/export async function POST/);
    expect(src).toContain("/sbar/jobs");
    expect(src).toMatch(/CORE_API_URL/);
  });

  it("UI proxy: events route streams text/event-stream", () => {
    const src = read(FILES.eventsRoute);
    expect(src).toMatch(/text\/event-stream/);
    expect(src).toMatch(/X-Accel-Buffering/);
    expect(src).toMatch(/\/sbar\/jobs\//);
  });

  it("UI proxy: assessments route forwards GET", () => {
    const src = read(FILES.assessmentRoute);
    expect(src).toMatch(/export async function GET/);
    expect(src).toMatch(/\/sbar\/assessments\//);
  });

  it("renders stage previews through the shared Markdown viewer with themed cards", () => {
    const src = read(FILES.playgroundComponent);
    // Tiptap-backed MarkdownEditor is the canonical viewer for any
    // patient-readable Markdown surface; reuse it instead of
    // pre-wrap monospace blobs.
    expect(src).toContain(
      'import MarkdownEditor from "@/components/markdown-editor/MarkdownEditor"',
    );
    // No raw pre-wrap dump for stage previews.
    expect(src).not.toMatch(/whiteSpace:\s*"pre-wrap"/);
    expect(src).not.toMatch(/ui-monospace,\s*SFMono-Regular/);
    // Per-stage themed cards (palette comes from the shared module).
    expect(src).toMatch(/STAGE_THEME/);
    // Stage previews render the markdown viewer in view mode.
    const viewMatches = src.match(/<MarkdownEditor[\s\S]*?mode="view"/g) ?? [];
    expect(viewMatches.length).toBeGreaterThanOrEqual(1);
  });

  it("delegates the final SBAR to the standalone SbarFinalDialog component", () => {
    const src = read(FILES.playgroundComponent);
    // Standalone view + dialog live in the shared module so other
    // applications can embed them without depending on the playground.
    expect(src).toMatch(/from\s+"@\/components\/sbar-final"/);
    expect(src).toContain("SbarFinalDialog");
    // No inline duplicate of the final cards in the playground itself.
    expect(src).not.toContain("data-testid={`sbar-final-section-${stage}`}");
    // The Done. status converts into a "View full SBAR" action button
    // when finalContent is available. The button is success-coloured
    // only when there are no errors; with errors it shifts to
    // warning. See VT-LEO-AI-514 TC-009.
    expect(src).toContain('data-testid="sbar-view-full-button"');
    expect(src).toMatch(/color=\{sbar\.errors\.length === 0 \? "success" : "warning"\}/);
  });

  // VT-LEO-AI-514 TC-008 / TC-009 -- structured errors[] / notices[]
  // surfaced from the orchestrator (DI-LEO-AI-516). Reviewers must
  // see plain-English error and notice Alerts above the result card,
  // and the result button must shift colour when errors are present.
  it("hook exposes errors and notices arrays populated from sbar_completed", () => {
    const src = read(FILES.hook);
    expect(src).toContain("export interface SbarErrorDetail");
    expect(src).toContain("export interface SbarNotice");
    expect(src).toMatch(/errors:\s*SbarErrorDetail\[\];/);
    expect(src).toMatch(/notices:\s*SbarNotice\[\];/);
    // The on('sbar_completed') handler reads the wire arrays.
    expect(src).toMatch(/Array\.isArray\(d\.errors\)/);
    expect(src).toMatch(/Array\.isArray\(d\.notices\)/);
    // Per-stage notices are appended as the stage finishes, not
    // only at the end.
    expect(src).toMatch(/d\.notice\s*\?\?\s*null/);
  });

  it("playground renders sbar-errors-alert and sbar-notices-alert with friendly text", () => {
    const src = read(FILES.playgroundComponent);
    expect(src).toContain('data-testid="sbar-errors-alert"');
    expect(src).toContain('data-testid="sbar-notices-alert"');
    // The errors Alert is severity='warning' (not error -- the run
    // produced a draft we want the reviewer to inspect, not abort).
    expect(src).toMatch(
      /sbar\.errors\.length > 0[\s\S]{0,200}severity="warning"[\s\S]{0,200}data-testid="sbar-errors-alert"/,
    );
    // The notices Alert is severity='info' (informational).
    expect(src).toMatch(
      /sbar\.notices\.length > 0[\s\S]{0,200}severity="info"[\s\S]{0,200}data-testid="sbar-notices-alert"/,
    );
    // No raw vendor strings should be referenced anywhere in the
    // playground source -- friendly text is built server side.
    expect(src).not.toMatch(/ValidationException/);
    expect(src).not.toMatch(/Converse operation/);
  });
});
