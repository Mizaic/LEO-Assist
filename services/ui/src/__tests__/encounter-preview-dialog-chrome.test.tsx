/**
 * VT-LEO-AI-214 -- /care/encounters preview wrapper (DI-LEO-AI-223).
 *
 * Static-source verification per ui-testing.mdc:
 *   - EncounterPreviewDialog opens as a read-only preview that
 *     renders the encounter text from item.text and the match
 *     rationale chrome WITHOUT calling any backend endpoint.
 *   - Matches of the reviewer's search query and the
 *     item.match_rationale terms are highlighted inside the
 *     encounter text via <mark> elements.
 *   - An explicit "Edit codes" footer button triggers
 *     createGoldLabelFromEncounter and mounts the shared
 *     GoldLabelEditorDialog in saveMode='dual', forwarding the
 *     match rationale via the dialog's headerChrome slot.
 *   - The shared GoldLabelDetailDialog accepts a headerChrome prop
 *     and renders it inside the dialog body.
 *   - EncounterMissionControl no longer prefetches coded links and
 *     forwards both onCodingChanged and the search query.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");

function read(rel: string): string {
  return fs.readFileSync(path.join(UI_SRC, rel), "utf-8");
}

describe("VT-LEO-AI-214 -- /care/encounters preview wrapper", () => {
  const PREVIEW_SRC = read(
    "components/mission-control/EncounterPreviewDialog.tsx",
  );
  const HOST_SRC = read(
    "components/mission-control/EncounterMissionControl.tsx",
  );
  const PANEL_SRC = read("components/gold-dataset/GoldDatasetPanel.tsx");

  it("TC-001: preview wrapper imports shared editor + dual-save helpers", () => {
    expect(PREVIEW_SRC).toContain('from "@/components/gold-editor"');
    expect(PREVIEW_SRC).toContain("GoldLabelEditorDialog");
    expect(PREVIEW_SRC).toContain("createGoldLabelFromEncounter");
    expect(PREVIEW_SRC).toContain("useDualSaveAdapter");
  });

  it("TC-002: read-only preview renders encounter text without an API call on open", () => {
    expect(PREVIEW_SRC).toContain('data-testid="encounter-preview-text"');
    expect(PREVIEW_SRC).toContain('data-testid="encounter-preview-empty"');
    expect(PREVIEW_SRC).toContain("EncounterTextBlock");
    // The seed call must only fire from the explicit handler. The
    // only useEffect in this file is the cancellation reset; confirm
    // there is exactly one useEffect, and it does NOT call the seed.
    const effectMatches = PREVIEW_SRC.match(/useEffect\(/g) ?? [];
    expect(effectMatches.length).toBe(1);
    expect(PREVIEW_SRC).toMatch(
      /useEffect\(\(\) => \{[\s\S]{0,120}if \(!item\) reset\(\);[\s\S]{0,120}\}, \[item, reset\]\);/,
    );
    expect(PREVIEW_SRC).toMatch(
      /handleEditCodes[\s\S]{0,400}createGoldLabelFromEncounter\(\{/,
    );
  });

  it("TC-003: 'Edit codes' button seeds gold label and mounts shared editor in dual-save mode", () => {
    expect(PREVIEW_SRC).toContain(
      'data-testid="encounter-preview-edit-codes"',
    );
    expect(PREVIEW_SRC).toMatch(
      /createGoldLabelFromEncounter\(\{[\s\S]{0,200}patient_id: item\.patient_id,[\s\S]{0,200}encounter_id: item\.encounter_id,/,
    );
    expect(PREVIEW_SRC).toContain("baseline_concept_ids: seed.baseline_concept_ids");
    expect(PREVIEW_SRC).toMatch(/saveMode="dual"/);
    expect(PREVIEW_SRC).toContain("entitySaver={dualSaver}");
    expect(PREVIEW_SRC).toContain("onAfterSave={");
  });

  it("TC-004: match rationale chrome is rendered in preview and forwarded via headerChrome", () => {
    expect(PREVIEW_SRC).toContain(
      "headerChrome={<MatchRationaleHeader item={item} />}",
    );
    expect(PREVIEW_SRC).toContain('data-testid="encounter-preview-rationale"');
    expect(PREVIEW_SRC).toContain("Why this matched your search");
  });

  it("TC-005: encounter text highlights search query and rationale terms via <mark>", () => {
    expect(PREVIEW_SRC).toContain("HighlightedText");
    expect(PREVIEW_SRC).toContain("collectHighlightTerms");
    expect(PREVIEW_SRC).toContain('component="mark"');
    expect(PREVIEW_SRC).toContain(
      'data-testid="encounter-preview-highlight"',
    );
    // Case-insensitive matching, length floor and longest-first sort
    // are all part of the contract.
    expect(PREVIEW_SRC).toMatch(/new RegExp\([\s\S]{0,300}"gi"[\s\S]{0,20}\)/);
    expect(PREVIEW_SRC).toContain("MIN_HIGHLIGHT_LEN");
    expect(PREVIEW_SRC).toMatch(/sort\(\(a, b\) => b\.length - a\.length\)/);
  });

  it("TC-006: seed failure keeps the preview open with an inline error", () => {
    expect(PREVIEW_SRC).toContain('data-testid="encounter-preview-error"');
    // editError must be rendered inside the preview body, never
    // replace the encounter text.
    expect(PREVIEW_SRC).toMatch(
      /<EncounterTextBlock[\s\S]{0,200}editError &&/,
    );
  });

  it("TC-007: GoldLabelDetailDialog renders headerChrome when provided", () => {
    expect(PANEL_SRC).toContain("headerChrome?: React.ReactNode;");
    expect(PANEL_SRC).toContain('data-testid="gold-dialog-header-chrome"');
  });

  it("TC-008: EncounterMissionControl does not prefetch coded links and forwards searchQuery", () => {
    expect(HOST_SRC).not.toContain("fetchEncounterCodedLinks");
    expect(HOST_SRC).not.toContain("previewCodedLinks");
    expect(HOST_SRC).not.toContain("previewLinksLoading");
    expect(HOST_SRC).not.toContain("previewLinksError");
    expect(HOST_SRC).toMatch(
      /<EncounterPreviewDialog[\s\S]{0,400}searchQuery=\{search\.query\}/,
    );
    expect(HOST_SRC).toMatch(
      /<EncounterPreviewDialog[\s\S]{0,500}onCodingChanged=\{\(\) => \{[\s\S]{0,80}loadAll\(false\);/,
    );
  });
});
