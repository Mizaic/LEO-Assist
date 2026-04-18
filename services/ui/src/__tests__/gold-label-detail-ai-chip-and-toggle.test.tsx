/**
 * VT-LEO-AI-201 TC-004 / TC-005 / TC-006 -- AI-suggested chip + show-original toggle.
 *
 * Static-source verification per ui-testing.mdc covering the
 * GoldLabelDetailDialog wiring inside GoldDatasetPanel.tsx and the
 * row-level "AI suggested" chip on CandidateReviewList.tsx.
 *
 * Pins:
 *   - per-entity ai-suggested-chip is rendered iff ai_first_pass_run_id is set
 *   - show-original-toggle flips the entity list to entities_json_original
 *   - the original snapshot view is rendered read-only (no save handlers)
 *   - the candidate row also surfaces an AI badge
 *   - GoldLabel + Candidate UI types both carry the AI audit fields
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function readUI(relative: string): string {
  return fs.readFileSync(path.join(ROOT, "services/ui/src", relative), "utf-8");
}

const PANEL_SRC = readUI("components/gold-dataset/GoldDatasetPanel.tsx");
const LIST_SRC = readUI(
  "components/gold-dataset/CandidateReviewList.tsx",
);
const TYPES_SRC = readUI("components/gold-dataset/goldDatasetTypes.ts");

describe("VT-201 -- AI-suggested chip + show-original toggle", () => {
  // -- VT-201-TC-004 ------------------------------------------------------
  it("TC-004: per-entity AI chip renders only when ai_first_pass_run_id is set", () => {
    expect(PANEL_SRC).toContain(
      "const isAISuggested = !!item.ai_first_pass_run_id;",
    );
    // The chip is gated on isAISuggested inside the per-entity row.
    expect(PANEL_SRC).toMatch(
      /\{isAISuggested && \([\s\S]{0,400}data-testid="ai-suggested-chip"/,
    );
  });

  // -- VT-201-TC-005 ------------------------------------------------------
  it("TC-005: show-original toggle flips between entities and originalEntities", () => {
    expect(PANEL_SRC).toContain(
      'const [showOriginalEntities, setShowOriginalEntities] = useState(false);',
    );
    expect(PANEL_SRC).toContain('data-testid="show-original-toggle"');
    expect(PANEL_SRC).toContain('data-testid="ai-suggested-banner"');
    // Original list is gated on showOriginalEntities being true.
    expect(PANEL_SRC).toMatch(
      /\{showOriginalEntities && \([\s\S]{0,400}data-testid="original-entities-list"/,
    );
    // AI list is gated on the inverse.
    expect(PANEL_SRC).toContain("{!showOriginalEntities && entities.map(");
  });

  // -- VT-201-TC-006 ------------------------------------------------------
  it("TC-006: original snapshot view is read-only (no commit/save handlers)", () => {
    const originalIdx = PANEL_SRC.indexOf('data-testid="original-entities-list"');
    expect(originalIdx).toBeGreaterThan(-1);
    // Take the slice from the read-only banner down to the next region
    // (the !showOriginalEntities entities map). This is the read-only
    // payload and must NOT wire up save / commit / mutation handlers.
    const closeIdx = PANEL_SRC.indexOf(
      "{!showOriginalEntities && entities.map(",
      originalIdx,
    );
    expect(closeIdx).toBeGreaterThan(originalIdx);
    const readonlyBlock = PANEL_SRC.slice(originalIdx, closeIdx);
    for (const banned of [
      "handleCommitEntityTerm",
      "handleUpdateEntityType",
      "saveSurfaceFormSynonym",
      "onChange",
      "onBlur",
    ]) {
      expect(readonlyBlock).not.toContain(banned);
    }
  });

  // -- Reset on candidate change -----------------------------------------
  it("resets showOriginalEntities to false when item.label_id changes", () => {
    // The resync useEffect is keyed on label_id and entities_json and
    // calls setShowOriginalEntities(false) so the toggle never leaks
    // across candidates.
    const effectIdx = PANEL_SRC.indexOf("prevLabelIdRef.current = item.label_id;");
    expect(effectIdx).toBeGreaterThan(-1);
    const effectBlock = PANEL_SRC.slice(effectIdx, effectIdx + 1500);
    expect(effectBlock).toContain("setShowOriginalEntities(false)");
  });

  // -- Row-level AI badge -------------------------------------------------
  it("CandidateReviewList renders an AI suggested chip on rows touched by the AI", () => {
    expect(LIST_SRC).toContain('data-testid="ai-suggested-chip"');
    expect(LIST_SRC).toContain('label="AI suggested"');
    expect(LIST_SRC).toContain("!!candidate.ai_first_pass_run_id");
  });

  // -- Type contracts -----------------------------------------------------
  it("Candidate and GoldLabel UI types carry the AI first-pass audit fields", () => {
    for (const field of [
      "ai_first_pass_run_id?:",
      "ai_first_pass_at?:",
      "entities_json_original?:",
    ]) {
      expect(TYPES_SRC).toContain(field);
      expect(PANEL_SRC).toContain(field);
    }
  });
});
