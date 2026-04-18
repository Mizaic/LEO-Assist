/**
 * VT-LEO-AI-215 -- Dry-run row 'Open in gold editor'
 * mounts the shared GoldLabelEditorDialog inline (DI-LEO-AI-222).
 *
 * Replaces the previous window.open / router.push deep-link contract.
 * The reviewer now stays on the console; clicking the pencil icon
 * fires POST /api/training/candidates/from-dry-run, takes the full
 * gold_label payload from the response, and mounts the shared dialog
 * inline so the dry-run table stays mounted in the background.
 *
 * Static-source verification per ui-testing.mdc.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function readUI(relative: string): string {
  return fs.readFileSync(path.join(ROOT, "services/ui/src", relative), "utf-8");
}

const EVALUATE_SRC = readUI("components/console/EvaluateStage.tsx");
const PANEL_SRC = readUI("components/gold-dataset/GoldDatasetPanel.tsx");
const PAGE_SRC = readUI("app/gold-dataset/page.tsx");

describe("VT-LEO-AI-215 -- Dry-run row 'Open in gold editor' inline dialog", () => {
  // -- VT-192-TC-001 -- icon imports retained ------------------------------
  it("TC-001: EvaluateStage imports IconButton + EditNoteIcon for the row pencil", () => {
    expect(EVALUATE_SRC).toMatch(
      /import IconButton from "@mui\/material\/IconButton";/,
    );
    expect(EVALUATE_SRC).toMatch(
      /import EditNoteIcon from "@mui\/icons-material\/EditNote";/,
    );
  });

  // -- VT-211-TC-002 -- new-tab workaround removed -------------------------
  it("TC-002: Evaluate stage no longer opens the gold editor in a new tab", () => {
    expect(EVALUATE_SRC).not.toMatch(/window\.open\s*\(/);
    expect(EVALUATE_SRC).not.toMatch(/aria-label="Open in gold editor \(new tab\)"/);
    expect(EVALUATE_SRC).not.toMatch(
      /import \{[^}]*useRouter[^}]*\} from "next\/navigation";/,
    );
  });

  // -- VT-192-TC-003 -- aria-label is the in-place wording -----------------
  it("TC-003: aria-label='Open in gold editor' appears on both row blocks", () => {
    const matches = EVALUATE_SRC.match(/aria-label="Open in gold editor"/g);
    expect(matches).not.toBeNull();
    expect((matches ?? []).length).toBeGreaterThanOrEqual(2);
  });

  // -- VT-211-TC-004 -- handler POSTs and stashes gold_label for inline mount
  it("TC-004: handler POSTs to from-dry-run and seeds the inline dialog target", () => {
    expect(EVALUATE_SRC).toContain("/api/training/candidates/from-dry-run");
    expect(EVALUATE_SRC).toContain("data?.gold_label");
    expect(EVALUATE_SRC).toMatch(
      /setGoldEditorTarget\(\s*goldLabel\s*\)/,
    );
  });

  // -- VT-211-TC-005 -- shared dialog mounted inline (saveMode='gold') -----
  it("TC-005: shared GoldLabelEditorDialog is imported and mounted inline", () => {
    expect(EVALUATE_SRC).toMatch(
      /import \{[\s\S]*?GoldLabelEditorDialog[\s\S]*?\} from "@\/components\/gold-editor"/,
    );
    expect(EVALUATE_SRC).toMatch(
      /<GoldLabelEditorDialog[\s\S]{0,800}saveMode="gold"[\s\S]{0,800}\/>/,
    );
    expect(EVALUATE_SRC).toMatch(
      /key=\{`evaluate-\$\{goldEditorTarget\.label_id\}`\}/,
    );
  });

  // -- VT-192-TC-006 -- IconButton guards in-flight + empty text -----------
  it("TC-006: IconButton disabled prop guards in-flight clicks and empty text", () => {
    expect(EVALUATE_SRC).toMatch(
      /disabled=\{[^}]*!text\.trim\(\)[^}]*openingGoldEditor === row\.encounter_id[^}]*\}/,
    );
  });

  // -- Legacy /gold-dataset?labelId deep link still supported --------------
  it("TC-007: GoldDatasetPanel still supports the labelId deep link for direct URLs", () => {
    expect(PANEL_SRC).toContain('searchParams?.get("labelId")');
    expect(PANEL_SRC).toMatch(/handledDeepLinkRef/);
    expect(PAGE_SRC).toMatch(/<Suspense[\s\S]*?>[\s\S]*?<GoldDatasetPanel\s*\/>[\s\S]*?<\/Suspense>/);
  });
});
