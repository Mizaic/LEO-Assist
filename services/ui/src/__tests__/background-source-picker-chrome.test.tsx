/**
 * VT-LEO-AI-232 -- BackgroundSourcePicker primitive (static-source layer)
 *
 * Pins the contracts of the patient-scoped picker (DI-LEO-AI-232 /
 * DO-LEO-AI-232) after it was reworked to reuse the Mission Control
 * encounter-text browsing capability (DI-LEO-AI-179, DI-LEO-AI-213):
 *   - the picker is a single unified feed (no Tabs)
 *   - it embeds the same sticky histogram timeline scrubber as
 *     /care/patients (`EncounterTimelineScrubber`)
 *   - the same filter helper (`applyCommonFilters`) drives Coded-only
 *     and free-text Search, so behaviour stays in lock-step
 *   - record kind is filtered via a single ToggleButtonGroup chip
 *     row (All / Encounters / Letters)
 *   - chunks render inside the document Collapse, never as a tab
 *   - the picker calls the patient-scoped endpoints only
 *   - the "chunks drop parent" rule still holds on confirm
 */
import fs from "fs";
import path from "path";

const PRIMITIVE = path.resolve(
  __dirname,
  "..",
  "components",
  "sbar-playground",
  "BackgroundSourcePicker.tsx",
);

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-232 BackgroundSourcePicker primitive", () => {
  it("has no Tabs and no per-tab data-testids (single unified feed)", () => {
    const src = read(PRIMITIVE);
    const tabIds = src.match(/background-source-picker-tab-[a-z]+/g) ?? [];
    expect(tabIds).toEqual([]);
    expect(src).not.toMatch(/<Tabs[\s>]/);
    expect(src).not.toMatch(/<Tab\s/);
  });

  it("reuses the Mission Control encounter-text scrubber and filter helper", () => {
    const src = read(PRIMITIVE);
    expect(src).toContain(
      'import EncounterTimelineScrubber from "@/components/mission-control/EncounterTimelineScrubber"',
    );
    expect(src).toContain(
      'import { applyCommonFilters } from "@/components/mission-control/encounterFilters"',
    );
    expect(src).toMatch(/<EncounterTimelineScrubber\b/);
    expect(src).toMatch(/applyCommonFilters\(/);
  });

  it("exposes the unified record-kind filter (All / Encounters / Letters)", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/data-testid="background-source-picker-kind-toggle"/);
    expect(src).toMatch(/data-testid="kind-toggle-all"/);
    expect(src).toMatch(/data-testid="kind-toggle-encounters"/);
    expect(src).toMatch(/data-testid="kind-toggle-documents"/);
  });

  it("exposes the Coded-only switch and free-text search box", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/data-testid="background-source-picker-coded-only"/);
    expect(src).toMatch(/data-testid="background-source-picker-search"/);
  });

  it("renders chunks inside a Collapse, not as a top-level tab", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/<Collapse[\s\S]*?<ChunkList/);
    expect(src).not.toMatch(/background-source-picker-tab-chunks/);
  });

  it("loads chunks via listDocumentReferenceChunks for the parent DocumentReference", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/listDocumentReferenceChunks\(documentReferenceId/);
  });

  it("implements 'chunks drop parent' rule on confirm", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/docsWithChunks/);
    expect(src).toMatch(/if \(docsWithChunks\.has\(id\)\) continue/);
  });
});
