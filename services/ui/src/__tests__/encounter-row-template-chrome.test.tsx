/**
 * VT-LEO-AI-512 -- /care/encounters dry-run row template + shared
 * HighlightedText primitive (DI-LEO-AI-514).
 *
 * Static-source verification per ui-testing.mdc. We assert on the
 * structural invariants of the refactored mission-control surface
 * and the new shared highlight module so the convergence between
 * /care/encounters, the patient drawer, and the dry-run candidates
 * queue cannot silently regress.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");

function read(rel: string): string {
  return fs.readFileSync(path.join(UI_SRC, rel), "utf-8");
}

describe("VT-LEO-AI-512 -- encounter row template + shared HighlightedText", () => {
  const HIGHLIGHT_SRC = read(
    "components/mission-control/HighlightedText.tsx",
  );
  const PREVIEW_SRC = read(
    "components/mission-control/EncounterPreviewDialog.tsx",
  );
  const CARD_SRC = read("components/mission-control/EncounterCard.tsx");
  const TEXT_UTILS_SRC = read(
    "components/mission-control/encounterTextUtils.tsx",
  );
  const TABLE_SRC = read(
    "components/mission-control/EncounterResultsTable.tsx",
  );
  const PANEL_SRC = read(
    "components/mission-control/EncounterSearchPanel.tsx",
  );

  it("TC-001: shared HighlightedText primitive exposes the documented contract", () => {
    expect(HIGHLIGHT_SRC).toMatch(/export function HighlightedText\b/);
    expect(HIGHLIGHT_SRC).toMatch(/export function collectHighlightTerms\b/);
    expect(HIGHLIGHT_SRC).toContain('component="mark"');
    expect(HIGHLIGHT_SRC).toContain('data-testid={testId}');
    // Default test id matches the value the new row template uses
    // and is the one consumed by browser-level tests.
    expect(HIGHLIGHT_SRC).toMatch(
      /testId\s*=\s*"encounter-highlight"/,
    );
    // Amber token shared with the patient drawer.
    expect(HIGHLIGHT_SRC).toMatch(/HIGHLIGHT_BG\s*=\s*"#fde68a"/);
    // Length floor + longest-first sort + case-insensitive regex.
    expect(HIGHLIGHT_SRC).toMatch(/MIN_HIGHLIGHT_LEN\s*=\s*3/);
    expect(HIGHLIGHT_SRC).toMatch(/sort\(\(a, b\) => b\.length - a\.length\)/);
    expect(HIGHLIGHT_SRC).toMatch(
      /new RegExp\([\s\S]{0,200}"gi"[\s\S]{0,20}\)/,
    );
  });

  it("TC-002: EncounterPreviewDialog imports the shared primitive (no inline copy)", () => {
    expect(PREVIEW_SRC).toContain("HighlightedText");
    expect(PREVIEW_SRC).toContain("collectHighlightTerms");
    expect(PREVIEW_SRC).toMatch(
      /import\s*\{[\s\S]{0,200}HighlightedText[\s\S]{0,200}\}\s*from\s*"\.\/HighlightedText"/,
    );
    // The inline helpers must be gone -- no second declaration of
    // collectHighlightTerms / HighlightedText / MIN_HIGHLIGHT_LEN
    // inside the dialog file.
    expect(PREVIEW_SRC).not.toMatch(/function collectHighlightTerms\(/);
    expect(PREVIEW_SRC).not.toMatch(/function HighlightedText\(/);
    expect(PREVIEW_SRC).not.toMatch(/const\s+MIN_HIGHLIGHT_LEN\b/);
  });

  it("TC-003: EncounterCard uses the shared primitive and the orphan helper is gone", () => {
    expect(CARD_SRC).toContain("HighlightedText");
    expect(CARD_SRC).toContain("collectHighlightTerms");
    expect(CARD_SRC).toMatch(
      /import\s*\{[\s\S]{0,200}HighlightedText[\s\S]{0,200}\}\s*from\s*"\.\/HighlightedText"/,
    );
    // The legacy drawer helper has been removed in favour of the
    // shared primitive (DI-LEO-AI-514).
    expect(CARD_SRC).not.toContain("highlightSearchMatches");
    expect(TEXT_UTILS_SRC).not.toMatch(/export function highlightSearchMatches/);
  });

  it("TC-004: EncounterResultsTable rebuilt around ReviewListCard", () => {
    expect(TABLE_SRC).toMatch(
      /import\s*\{[\s\S]{0,160}ReviewListCard[\s\S]{0,160}\}\s*from\s*"@leo\/design-system"/,
    );
    expect(TABLE_SRC).toContain("ReviewListItem");
    // No more MUI Table primitives -- we now render a single
    // ReviewListCard with rows. The TableHead/TableRow imports must
    // be gone so the visual template cannot drift back to a table.
    expect(TABLE_SRC).not.toMatch(/from "@mui\/material\/Table"/);
    expect(TABLE_SRC).not.toMatch(/from "@mui\/material\/TableRow"/);
    expect(TABLE_SRC).not.toMatch(/from "@mui\/material\/TableHead"/);
    // Tone vocabulary helper must encode the documented mapping.
    expect(TABLE_SRC).toMatch(/export function toneFor\b/);
    expect(TABLE_SRC).toMatch(/status === "failed"[\s\S]{0,40}return "danger"/);
    expect(TABLE_SRC).toMatch(/coded_count >= 1[\s\S]{0,40}return "positive"/);
    expect(TABLE_SRC).toMatch(/hasActiveQuery[\s\S]{0,40}return "warning"/);
  });

  it("TC-005: row title uses HighlightedText; chips slot composes the documented chips", () => {
    expect(TABLE_SRC).toMatch(
      /<HighlightedText\s+text=\{text\}\s+terms=\{isDemoMode\s*\?\s*\[\]\s*:\s*highlightTerms\}\s*\/>/,
    );
    // chips slot is built by rowChips(); confirm the four chip
    // groups (match-type, coded count, status, rationale slice 4)
    // are all present.
    expect(TABLE_SRC).toMatch(/MATCH_CHIP\[row\.match_type\]/);
    expect(TABLE_SRC).toContain("`${row.coded_count} coded`");
    expect(TABLE_SRC).toMatch(
      /row\.match_rationale\?\.slice\(0,\s*4\)/,
    );
    expect(TABLE_SRC).toContain("STATUS_CHIP[status]");
  });

  it("TC-006: selection checkbox is in the actions slot and stops row click propagation", () => {
    // Actions slot is built by rowActions(). The checkbox must call
    // stopPropagation on click so toggling selection does not also
    // open the preview dialog.
    expect(TABLE_SRC).toMatch(/function rowActions\(/);
    expect(TABLE_SRC).toMatch(
      /<Checkbox[\s\S]{0,400}onClick=\{\(e\)\s*=>\s*e\.stopPropagation\(\)\}/,
    );
    expect(TABLE_SRC).toMatch(
      /actions:\s*rowActions\(row,\s*isSelected,\s*onToggleSelection\)/,
    );
    // Row activation still opens the preview.
    expect(TABLE_SRC).toMatch(/onSelect:\s*\(\)\s*=>\s*onOpenPreview\(row\)/);
  });

  it("TC-007: search box ships a clear-button end-adornment when query is non-empty", () => {
    expect(PANEL_SRC).toContain("CloseIcon");
    expect(PANEL_SRC).toMatch(
      /endAdornment:\s*state\.query\s*\?\s*\(/,
    );
    expect(PANEL_SRC).toContain('data-testid="encounter-search-clear"');
    expect(PANEL_SRC).toMatch(/onClick=\{\(\)\s*=>\s*onQueryChange\(""\)\}/);
  });

  it("TC-008: empty state echoes the query when no rows match an active query", () => {
    expect(TABLE_SRC).toContain('"encounter-empty-query"');
    expect(TABLE_SRC).toContain('Nothing matches "');
    expect(TABLE_SRC).toContain("Try different words.");
    // The empty branch must render only when there are no rows AND
    // an active query is set.
    expect(TABLE_SRC).toMatch(
      /hasActiveQuery\s*\?\s*"encounter-empty-query"\s*:\s*"encounter-empty-default"/,
    );
    // Empty branch is gated on rows.length === 0.
    expect(TABLE_SRC).toMatch(/if \(rows\.length === 0\)/);
  });
});
