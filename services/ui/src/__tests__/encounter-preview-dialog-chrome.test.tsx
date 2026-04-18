/**
 * VT-LEO-AI-212 -- /care/encounters preview wrapper (DI-LEO-AI-212).
 *
 * Static-source verification per ui-testing.mdc:
 *   - EncounterPreviewDialog is a thin wrapper that mounts the shared
 *     GoldLabelEditorDialog in dual-save mode for the
 *     /care/encounters mission-control surface.
 *   - It seeds the gold label via createGoldLabelFromEncounter and
 *     wires the dual-save adapter.
 *   - It surfaces match-rationale chips through the dialog's
 *     headerChrome slot so reviewers retain the search context.
 *   - The legacy coded-links prefetch on EncounterMissionControl is
 *     gone; it relied on data the new editor seeds itself.
 *   - The shared GoldLabelDetailDialog accepts a headerChrome prop and
 *     renders it inside the dialog body.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");

function read(rel: string): string {
  return fs.readFileSync(path.join(UI_SRC, rel), "utf-8");
}

describe("VT-LEO-AI-212 -- /care/encounters preview wrapper", () => {
  const PREVIEW_SRC = read(
    "components/mission-control/EncounterPreviewDialog.tsx",
  );
  const HOST_SRC = read(
    "components/mission-control/EncounterMissionControl.tsx",
  );
  const PANEL_SRC = read("components/gold-dataset/GoldDatasetPanel.tsx");

  it("TC-001: preview wrapper imports shared editor + dual-save helpers", () => {
    expect(PREVIEW_SRC).toContain(
      'from "@/components/gold-editor"',
    );
    expect(PREVIEW_SRC).toContain("GoldLabelEditorDialog");
    expect(PREVIEW_SRC).toContain("createGoldLabelFromEncounter");
    expect(PREVIEW_SRC).toContain("useDualSaveAdapter");
  });

  it("TC-002: wrapper seeds the gold label from the live encounter", () => {
    expect(PREVIEW_SRC).toMatch(
      /createGoldLabelFromEncounter\(\{[\s\S]{0,150}patient_id: item\.patient_id,[\s\S]{0,150}encounter_id: item\.encounter_id,/,
    );
    expect(PREVIEW_SRC).toContain("setContext({");
    expect(PREVIEW_SRC).toContain("baseline_concept_ids: seed.baseline_concept_ids");
  });

  it("TC-003: wrapper mounts the shared editor in saveMode='dual'", () => {
    expect(PREVIEW_SRC).toMatch(/saveMode="dual"/);
    expect(PREVIEW_SRC).toContain("entitySaver={dualSaver}");
    expect(PREVIEW_SRC).toContain("onAfterSave={");
  });

  it("TC-004: match rationale chrome is passed via headerChrome", () => {
    expect(PREVIEW_SRC).toContain("headerChrome={<MatchRationaleHeader item={item} />}");
    expect(PREVIEW_SRC).toContain("data-testid=\"encounter-preview-rationale\"");
    expect(PREVIEW_SRC).toContain("Why this matched your search");
  });

  it("TC-005: GoldLabelDetailDialog renders headerChrome when provided", () => {
    expect(PANEL_SRC).toContain("headerChrome?: React.ReactNode;");
    expect(PANEL_SRC).toContain("data-testid=\"gold-dialog-header-chrome\"");
  });

  it("TC-006: EncounterMissionControl no longer prefetches coded links for preview", () => {
    expect(HOST_SRC).not.toContain("fetchEncounterCodedLinks");
    expect(HOST_SRC).not.toContain("previewCodedLinks");
    expect(HOST_SRC).not.toContain("previewLinksLoading");
    expect(HOST_SRC).not.toContain("previewLinksError");
  });

  it("TC-007: EncounterMissionControl forwards onCodingChanged to refresh the list", () => {
    expect(HOST_SRC).toMatch(
      /<EncounterPreviewDialog[\s\S]{0,400}onCodingChanged=\{\(\) => \{[\s\S]{0,80}loadAll\(false\);/,
    );
  });
});
