/**
 * Static-source VT: Pipeline tab shows live facts/codes and classified errors.
 *
 * Atlas: DI-257D6883 / DO-158BE606 / VT-825F42CC
 */
import * as fs from "fs";
import * as path from "path";

const ROOT = path.join(__dirname, "../app/admin/validation-lab/inspector");
const PANEL = path.join(ROOT, "RunInspectorPanel.tsx");
const WIZARD = path.join(ROOT, "PipelineWizard.tsx");
const DETAIL = path.join(ROOT, "StageDetailPane.tsx");
const WORK = path.join(ROOT, "StageWorkPreview.tsx");
const EVIDENCE = path.join(ROOT, "StageStoryPanel.tsx");
const EXTRA = path.join(ROOT, "StageExtraDetail.tsx");
const STORY = path.join(ROOT, "stageEvidence.ts");
const TIP = path.join(ROOT, "EvidenceTooltip.tsx");
const CHIPS = path.join(ROOT, "StateKeyChips.tsx");
const SCHEMA_CHIP = path.join(ROOT, "formSchemaChip.ts");

describe("RunInspectorPanel -- Pipeline tab with process-mining wizard", () => {
  let src: string;
  let chips: string;
  beforeAll(() => {
    src = [
      fs.readFileSync(PANEL, "utf-8"),
      fs.readFileSync(WIZARD, "utf-8"),
      fs.readFileSync(DETAIL, "utf-8"),
      fs.readFileSync(WORK, "utf-8"),
      fs.readFileSync(EVIDENCE, "utf-8"),
      fs.readFileSync(EXTRA, "utf-8"),
      fs.readFileSync(STORY, "utf-8"),
      fs.readFileSync(TIP, "utf-8"),
    ].join("\n");
    chips = fs.readFileSync(CHIPS, "utf-8");
  });

  it("has a Pipeline tab label", () => {
    expect(src).toMatch(/Pipeline/);
  });

  it("renders PipelineWizard in the pipeline tab", () => {
    expect(src).toMatch(/PipelineWizard/);
  });

  it("walks stages in order and locks later steps", () => {
    expect(src).toMatch(/validation-lab-next-step/);
    expect(src).toMatch(/canOpenStep/);
    expect(src).toMatch(/Review earlier steps first/);
    expect(src).toMatch(/data-locked/);
  });

  it("has a stage rail showing each span", () => {
    expect(src).toMatch(/stage.rail|Stage rail|Stages/i);
  });

  it("uses plain English stage names and a focus question", () => {
    expect(src).toMatch(/plainStageCopy/);
    expect(src).toMatch(/\.question/);
  });

  it("shows telemetry (worker, started_at, duration)", () => {
    expect(src).toMatch(/worker_id|started_at|duration_ms/);
  });

  it("shows input and output keys per stage", () => {
    expect(src).toMatch(/input_keys/);
    expect(src).toMatch(/output_keys/);
    expect(src).toMatch(/StateKeyChips/);
  });

  it("loads stage values so present keys can be shown", () => {
    expect(src).toMatch(/stageDetail/);
    expect(src).toMatch(/valuesReady/);
  });

  it("marks present keys green and shows a value tooltip", () => {
    expect(chips).toMatch(/Tooltip/);
    expect(chips).toMatch(/#DCFCE7/);
    expect(chips).toMatch(/#F8FAFC/);
    expect(chips).toMatch(/data-present/);
    expect(chips).toMatch(/aria-label/);
  });

  it("keeps the value tooltip inside the viewport and scrollable", () => {
    expect(chips).toMatch(/disableInteractive=\{false\}/);
    expect(chips).toMatch(/maxHeight:\s*"calc\(100vh - 16px\)"/);
    expect(chips).toMatch(/overflow:\s*"auto"/);
    expect(chips).toMatch(/preventOverflow/);
    expect(chips).not.toMatch(/maxHeight:\s*240/);
  });

  it("expands entity lists into fact and code chips", () => {
    expect(chips).toMatch(/validation-lab-entity-chip/);
    expect(chips).toMatch(/itemsFromEntities/);
  });

  it("opens the taught form schema from the form_schema chip", () => {
    const href = fs.readFileSync(SCHEMA_CHIP, "utf-8");
    expect(chips).toMatch(/formSchemaViewHref/);
    expect(href).toMatch(/form_schema_fingerprint/);
    expect(href).toMatch(/\/admin\/knowledge\?tab=form-templates/);
    expect(href).toMatch(/fingerprint=/);
  });

  it("Fix in Pipeline Guards link points to guard-rules tab", () => {
    expect(src).toMatch(/tab=guard-rules|Fix in Pipeline Guards/);
    expect(fs.readFileSync(PANEL, "utf-8")).toMatch(/tab=guard-rules/);
  });

  it("shows facts and codes as they arrive", () => {
    expect(src).toMatch(/StageWorkPreview/);
    expect(src).toMatch(/work_preview|workPreviewFromStage/);
    expect(src).toMatch(/validation-lab-stage-work/);
  });

  it("keeps fact-chip tooltip text light on a dark panel", () => {
    const tip = fs.readFileSync(TIP, "utf-8");
    expect(tip).toMatch(/#0F172A/);
    expect(tip).toMatch(/#F8FAFC/);
    expect(tip).toMatch(/From the letter/);
    expect(tip).toMatch(/Words found/);
    expect(tip).toMatch(/Context/);
    expect(tip).toMatch(/Kind/);
  });

  it("shows a classified reason when draft assessment fails", () => {
    expect(src).toMatch(/Reason code/);
    expect(src).toMatch(/parseSbarStageError/);
  });
});
