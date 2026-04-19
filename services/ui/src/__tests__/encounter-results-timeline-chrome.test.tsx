/**
 * VT-LEO-AI-515 -- /care/encounters timeline brush wrapper + host
 * wiring (DI-LEO-AI-516).
 *
 * Static-source verification per ui-testing.mdc. The wrapper lifts
 * the patient-drawer EncounterTimelineScrubber primitive onto the
 * /care/encounters search-results surface; this test asserts on the
 * structural invariants of the wrapper module and the host wiring
 * (timelineRange state, filter intersection, jump-to-preview, and
 * the active-row highlight) so the convergence with the drawer
 * scrubber cannot silently regress.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");

function read(rel: string): string {
  return fs.readFileSync(path.join(UI_SRC, rel), "utf-8");
}

describe("VT-LEO-AI-515 -- /care/encounters timeline brush wrapper", () => {
  const WRAPPER_SRC = read(
    "components/mission-control/EncounterResultsTimeline.tsx",
  );
  const HOST_SRC = read(
    "components/mission-control/EncounterMissionControl.tsx",
  );

  it("TC-001: wrapper module exposes the documented adapter contract", () => {
    expect(WRAPPER_SRC).toMatch(
      /import\s+EncounterTimelineScrubber\s+from\s+["']\.\/EncounterTimelineScrubber["']/,
    );
    expect(WRAPPER_SRC).toMatch(
      /import\s+type\s+\{\s*ScrubberEncounter\s*\}\s+from\s+["']\.\/timelineBins["']/,
    );
    expect(WRAPPER_SRC).toMatch(
      /export default function EncounterResultsTimeline\b/,
    );
    // Forwards the no-episode-context defaults to the scrubber.
    expect(WRAPPER_SRC).toMatch(/linkedEncounterIds=\{\s*EMPTY_LINKED\s*\}/);
    expect(WRAPPER_SRC).toMatch(/episodeFrom=\{\s*null\s*\}/);
    expect(WRAPPER_SRC).toMatch(/episodeTo=\{\s*null\s*\}/);
    expect(WRAPPER_SRC).toMatch(/milestones=\{\s*EMPTY_MILESTONES\s*\}/);
    expect(WRAPPER_SRC).toMatch(/EMPTY_LINKED[^\n]*=\s*new Set/);
  });

  it("TC-002: adapter maps encounter_date -> date, drops null dates, and memoises", () => {
    expect(WRAPPER_SRC).toMatch(/useMemo<ScrubberEncounter\[\]>/);
    expect(WRAPPER_SRC).toMatch(/Date\.parse\s*\(\s*row\.encounter_date/);
    expect(WRAPPER_SRC).toMatch(/Number\.isFinite\s*\(\s*ts\s*\)/);
    expect(WRAPPER_SRC).toMatch(/encounter_id:\s*String\(row\.encounter_id\)/);
    expect(WRAPPER_SRC).toMatch(/date:\s*row\.encounter_date as string/);
  });

  it("TC-003: wrapper renders nothing when fewer than 5 dated rows are loaded", () => {
    expect(WRAPPER_SRC).toMatch(/MIN_DATED_ROWS\s*=\s*5/);
    expect(WRAPPER_SRC).toMatch(
      /scrubberRows\.length\s*<\s*MIN_DATED_ROWS[\s\S]{0,40}return null/,
    );
  });

  it("TC-004: host holds controlled timelineRange state and clears it on load", () => {
    expect(HOST_SRC).toMatch(
      /useState<\s*\{\s*fromMs:\s*number;\s*toMs:\s*number\s*\}\s*\|\s*null\s*>\(null\)/,
    );
    // The reset lives inside the loadAll() path so a fresh search
    // always opens unfiltered.
    expect(HOST_SRC).toMatch(/setTimelineRange\(null\)/);
  });

  it("TC-005: brush filter composes with bucket filter BEFORE pagination", () => {
    // filteredRows useMemo depends on both filters and applies the
    // timeline window via Date.parse on encounter_date.
    expect(HOST_SRC).toMatch(
      /const filteredRows = useMemo\([\s\S]*?bucketFilter[\s\S]*?timelineRange[\s\S]*?\}\s*,\s*\[\s*rows\s*,\s*bucketFilter\s*,\s*timelineRange\s*\]\s*\)/,
    );
    expect(HOST_SRC).toMatch(
      /Date\.parse\s*\(\s*r\.encounter_date[\s\S]{0,200}timelineRange\.fromMs/,
    );
    // Pagination still slices filteredRows -- no shortcut on rows.
    expect(HOST_SRC).toMatch(
      /displayRows\s*=\s*useMemo\([\s\S]*?filteredRows\.slice\(/,
    );
  });

  it("TC-006: active preview drives table highlight and timeline active ring", () => {
    expect(HOST_SRC).toMatch(
      /highlightedEncounterId=\{\s*activePreview\?\.encounter_id\s*\?\?\s*null\s*\}/,
    );
    expect(HOST_SRC).toMatch(
      /activeEncounterId=\{\s*activePreview\?\.encounter_id\s*\?\?\s*null\s*\}/,
    );
  });

  it("TC-007: timeline jump opens the preview dialog for the matching loaded row", () => {
    expect(HOST_SRC).toMatch(/handleTimelineJump\b/);
    expect(HOST_SRC).toMatch(
      /handleTimelineJump\s*=\s*useCallback\([\s\S]{0,400}rows\.find\([\s\S]{0,200}setActivePreview\(target\)/,
    );
    expect(HOST_SRC).toMatch(
      /<EncounterResultsTimeline[\s\S]*?onJumpToEncounter=\{\s*handleTimelineJump\s*\}/,
    );
  });

  it("TC-008: wrapper passes through the controlled brush range to the scrubber", () => {
    expect(WRAPPER_SRC).toMatch(
      /visibleFromMs=\{\s*visibleFromMs\s*\}/,
    );
    expect(WRAPPER_SRC).toMatch(
      /visibleToMs=\{\s*visibleToMs\s*\}/,
    );
    expect(WRAPPER_SRC).toMatch(
      /onVisibleRangeChange=\{\s*onVisibleRangeChange\s*\}/,
    );
    // Host hands down the controlled props from its timelineRange state.
    expect(HOST_SRC).toMatch(
      /<EncounterResultsTimeline[\s\S]*?visibleFromMs=\{\s*timelineRange\?\.fromMs\s*\?\?\s*null\s*\}/,
    );
    expect(HOST_SRC).toMatch(
      /<EncounterResultsTimeline[\s\S]*?visibleToMs=\{\s*timelineRange\?\.toMs\s*\?\?\s*null\s*\}/,
    );
    expect(HOST_SRC).toMatch(
      /<EncounterResultsTimeline[\s\S]*?onVisibleRangeChange=\{\s*handleTimelineRangeChange\s*\}/,
    );
  });
});
