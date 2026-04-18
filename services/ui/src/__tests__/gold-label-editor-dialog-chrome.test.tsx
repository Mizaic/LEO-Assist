/**
 * VT-LEO-AI-213 -- Shared GoldLabelEditorDialog surface (DI-LEO-AI-219).
 *
 * Static-source verification per ui-testing.mdc:
 *   - The shared module re-exports the dialog under a stable name.
 *   - The dialog accepts saveMode + entitySaver + onAfterSave props
 *     and defaults to the "gold" mode + the default PATCH saver so
 *     the candidates tab and other existing call sites stay unchanged.
 *   - The dual-save warning banner only renders in saveMode === "dual".
 *   - The shared barrel surfaces useDualSaveAdapter and the four
 *     gold-editor API helpers.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");

function read(rel: string): string {
  return fs.readFileSync(path.join(UI_SRC, rel), "utf-8");
}

describe("VT-LEO-AI-213 -- shared GoldLabelEditorDialog surface", () => {
  const PANEL_SRC = read("components/gold-dataset/GoldDatasetPanel.tsx");
  const DIALOG_SRC = read("components/gold-editor/GoldLabelEditorDialog.tsx");
  const INDEX_SRC = read("components/gold-editor/index.ts");
  const TYPES_SRC = read("components/gold-editor/types.ts");
  const API_SRC = read("components/gold-editor/api.ts");
  const ADAPTER_SRC = read("components/gold-editor/useDualSaveAdapter.ts");

  it("TC-001: dialog is exported from GoldDatasetPanel for cross-surface reuse", () => {
    expect(PANEL_SRC).toMatch(/export function GoldLabelDetailDialog\(/);
  });

  it("TC-002: dialog accepts saveMode/entitySaver/onAfterSave with safe defaults", () => {
    expect(PANEL_SRC).toContain("saveMode = \"gold\",");
    expect(PANEL_SRC).toMatch(/saveMode\?: GoldDialogSaveMode;/);
    expect(PANEL_SRC).toMatch(/entitySaver\?: GoldDialogEntitySaver;/);
    expect(PANEL_SRC).toMatch(/onAfterSave\?: \(\) => void;/);
  });

  it("TC-003: persistEntities prefers entitySaver when provided, else falls back to PATCH", () => {
    expect(PANEL_SRC).toMatch(
      /if \(entitySaver\) \{[\s\S]{0,200}await entitySaver\(payload\);[\s\S]{0,200}\} else \{[\s\S]{0,200}await patchGoldLabelEntities\(item\.label_id, payload\);/,
    );
    expect(PANEL_SRC).toContain("onAfterSave?.();");
  });

  it("TC-004: dual-save warning banner is gated on saveMode === 'dual'", () => {
    expect(PANEL_SRC).toMatch(
      /\{saveMode === "dual" && \([\s\S]{0,400}data-testid="dual-save-banner"/,
    );
    expect(PANEL_SRC).toContain("R-LEO-AI-206");
  });

  it("TC-005: shared barrel re-exports the dialog as GoldLabelEditorDialog", () => {
    expect(DIALOG_SRC).toContain(
      'import { GoldLabelDetailDialog } from "@/components/gold-dataset/GoldDatasetPanel";',
    );
    expect(DIALOG_SRC).toContain(
      "export { GoldLabelDetailDialog as GoldLabelEditorDialog };",
    );
    expect(INDEX_SRC).toContain(
      'export { GoldLabelEditorDialog, default } from "./GoldLabelEditorDialog";',
    );
  });

  it("TC-006: shared barrel surfaces dual-save helpers and types", () => {
    for (const symbol of [
      "useDualSaveAdapter",
      "patchGoldLabelEntities",
      "createGoldLabelFromDryRun",
      "createGoldLabelFromEncounter",
      "syncCodedLinksFromGold",
    ]) {
      expect(INDEX_SRC).toContain(symbol);
    }
    for (const t of [
      "GoldLabel",
      "Entity",
      "EntityRelation",
      "SavedGoldEntity",
      "GoldDialogSaveMode",
      "GoldDialogEntitySaver",
      "DualSaveEncounterContext",
    ]) {
      expect(INDEX_SRC).toContain(t);
    }
  });

  it("TC-007: types module sources GoldLabel from goldDatasetTypes (single-source-of-truth)", () => {
    expect(TYPES_SRC).toContain('from "@/components/gold-dataset/goldDatasetTypes"');
    expect(TYPES_SRC).toMatch(/DualSaveEncounterContext[\s\S]{0,400}baseline_concept_ids: string\[\]/);
  });

  it("TC-008: api helpers target the documented endpoints", () => {
    expect(API_SRC).toContain("/api/training/gold-labels/");
    expect(API_SRC).toContain("/api/training/candidates/from-dry-run");
    expect(API_SRC).toContain("/api/training/gold-labels/from-encounter");
    expect(API_SRC).toContain("/coded-links/sync-from-gold");
  });

  it("TC-009: useDualSaveAdapter posts the baseline + advances it after sync", () => {
    expect(ADAPTER_SRC).toContain("expected_baseline_concept_ids: baselineRef.current");
    expect(ADAPTER_SRC).toContain(
      "baselineRef.current = result.baseline_concept_ids;",
    );
  });
});
