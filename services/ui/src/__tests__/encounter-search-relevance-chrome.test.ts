/**
 * VT-LEO-AI-519 -- Drawer encounter search: shared relevance utility
 * + match rationale chips (DI-LEO-AI-520).
 *
 * Static-source verification per ui-testing.mdc. The shared
 * encounterRelevance.ts module mirrors the deterministic part of the
 * /care/encounters server query understanding so the patient drawer
 * picks up the same typo correction, synonym expansion, and "why this
 * matched" chip taxonomy as the host search. This test asserts the
 * structural invariants of the new module, the applyCommonFilters
 * rewire, and the EncounterCard chip integration so the convergence
 * cannot silently regress.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");

function read(rel: string): string {
  return fs.readFileSync(path.join(UI_SRC, rel), "utf-8");
}

describe("VT-LEO-AI-519 -- drawer encounter search relevance utility", () => {
  const RELEVANCE_SRC = read(
    "components/mission-control/encounterRelevance.ts",
  );
  const FILTERS_SRC = read(
    "components/mission-control/encounterFilters.ts",
  );
  const CARD_SRC = read("components/mission-control/EncounterCard.tsx");

  it("TC-001: encounterRelevance.ts exports the documented surface", () => {
    expect(RELEVANCE_SRC).toMatch(/export function expandSearchTerms\b/);
    expect(RELEVANCE_SRC).toMatch(/export function computeMatchRationale\b/);
    expect(RELEVANCE_SRC).toMatch(/export function hasAnyExpandedHit\b/);
    expect(RELEVANCE_SRC).toMatch(/export interface MatchRationale\b/);
  });

  it("TC-002: module mirrors the server's TYPO_MAP and SYNONYM_MAP entries", () => {
    expect(RELEVANCE_SRC).toMatch(/TYPO_MAP[\s\S]{0,400}breat:\s*"breast"/);
    expect(RELEVANCE_SRC).toMatch(/wight:\s*"weight"/);
    expect(RELEVANCE_SRC).toMatch(/lums:\s*"lumps"/);
    expect(RELEVANCE_SRC).toMatch(/tumor:\s*"tumour"/);
    expect(RELEVANCE_SRC).toMatch(
      /SYNONYM_MAP[\s\S]{0,800}breast:\s*\[\s*"breast",\s*"mammary"\s*\]/,
    );
    expect(RELEVANCE_SRC).toMatch(
      /lump:\s*\[\s*"lump",\s*"mass",\s*"swelling",\s*"nodule"\s*\]/,
    );
    expect(RELEVANCE_SRC).toMatch(
      /weight:\s*\[\s*"weight",\s*"weightloss",\s*"weight_loss",\s*"cachexia"\s*\]/,
    );
    expect(RELEVANCE_SRC).toMatch(
      /loss:\s*\[\s*"loss",\s*"losing",\s*"reduced"\s*\]/,
    );
    expect(RELEVANCE_SRC).toMatch(/cough:\s*\[\s*"cough",\s*"coughing"\s*\]/);
    expect(RELEVANCE_SRC).toMatch(
      /bleeding:\s*\[\s*"bleeding",\s*"blood_loss",\s*"haemorrhage",\s*"hemorrhage"\s*\]/,
    );
  });

  it("TC-003: expandSearchTerms applies typo correction before synonym expansion", () => {
    // The token loop must apply TYPO_MAP first, then look up SYNONYM_MAP.
    expect(RELEVANCE_SRC).toMatch(
      /function normaliseTokens[\s\S]{0,300}TYPO_MAP\[tok\]\s*\?\?\s*tok/,
    );
    expect(RELEVANCE_SRC).toMatch(
      /expandSearchTerms[\s\S]{0,800}normaliseTokens\(query\)[\s\S]{0,400}SYNONYM_MAP\[tok\]\s*\?\?\s*\[tok\]/,
    );
  });

  it("TC-004: expandSearchTerms returns [] for blank input and respects the 12/36 caps", () => {
    expect(RELEVANCE_SRC).toMatch(/if\s*\(!query\)\s*return\s*\[\]/);
    expect(RELEVANCE_SRC).toMatch(/MAX_TERMS\s*=\s*12/);
    expect(RELEVANCE_SRC).toMatch(/MAX_EXPANDED\s*=\s*MAX_TERMS\s*\*\s*3/);
    expect(RELEVANCE_SRC).toMatch(/\.slice\(0,\s*MAX_TERMS\)/);
    expect(RELEVANCE_SRC).toMatch(
      /out\.length\s*>=\s*MAX_EXPANDED[\s\S]{0,80}return\s+out/,
    );
  });

  it("TC-005: computeMatchRationale matches the server feature_match_rationale shape", () => {
    expect(RELEVANCE_SRC).toMatch(
      /computeMatchRationale[\s\S]{0,800}termHits:\s*0[\s\S]{0,80}hitTerms:\s*\[\][\s\S]{0,80}termCoverage:\s*0/,
    );
    expect(RELEVANCE_SRC).toMatch(/hits\.slice\(0,\s*8\)/);
    expect(RELEVANCE_SRC).toMatch(
      /termCoverage:\s*hits\.length\s*\/\s*Math\.max\(1,\s*expandedTerms\.length\)/,
    );
  });

  it("TC-006: applyCommonFilters delegates to expandSearchTerms + hasAnyExpandedHit", () => {
    expect(FILTERS_SRC).toMatch(
      /import\s+\{\s*expandSearchTerms,\s*hasAnyExpandedHit\s*\}\s+from\s+["']\.\/encounterRelevance["']/,
    );
    // Multi-chip path (DI-B12A48EA): each chip is individually expanded.
    // expandSearchTerms is called per chip inside a for..of loop.
    expect(FILTERS_SRC).toMatch(
      /const\s+expandedTerms\s*=\s*expandSearchTerms\(chip\)/,
    );
    expect(FILTERS_SRC).toMatch(
      /hasAnyExpandedHit\(e\.text,\s*expandedTerms\)/,
    );
    // Guard against the previous bare-substring path coming back.
    expect(FILTERS_SRC).not.toMatch(
      /\(e\.text\s*\?\?\s*""\)\.toLowerCase\(\)\.includes\(query\)/,
    );
  });

  it("TC-007: EncounterCard wires expanded terms into the highlighter", () => {
    expect(CARD_SRC).toMatch(
      /import\s+\{\s*computeMatchRationale,\s*expandSearchTerms,?\s*\}\s+from\s+["']\.\/encounterRelevance["']/,
    );
    expect(CARD_SRC).toMatch(
      /const\s+expandedTerms\s*=\s*useMemo\([\s\S]{0,80}expandSearchTerms\(search\)/,
    );
    expect(CARD_SRC).toMatch(
      /matchRationale\s*=\s*useMemo\([\s\S]{0,120}computeMatchRationale\(enc\.text,\s*expandedTerms\)/,
    );
    expect(CARD_SRC).toMatch(
      /collectHighlightTerms\(search,\s*matchRationale\.hitTerms\)/,
    );
  });

  it("TC-008: EncounterCard renders the rationale chip row capped at 4", () => {
    expect(CARD_SRC).toMatch(
      /showRationaleChips\s*=\s*expandedTerms\.length\s*>\s*0\s*&&\s*matchRationale\.hitTerms\.length\s*>\s*0/,
    );
    expect(CARD_SRC).toMatch(
      /data-testid="encounter-card-match-rationale"/,
    );
    expect(CARD_SRC).toMatch(
      /matchRationale\.hitTerms\.slice\(0,\s*4\)\.map/,
    );
    expect(CARD_SRC).toMatch(
      /data-testid="encounter-card-match-rationale-chip"/,
    );
    expect(CARD_SRC).toMatch(/variant="outlined"/);
    // Match the visual token (height 20, fontSize 0.65rem) used by the
    // host row chips so the two surfaces feel identical.
    expect(CARD_SRC).toMatch(
      /encounter-card-match-rationale-chip[\s\S]{0,400}height:\s*20/,
    );
    expect(CARD_SRC).toMatch(
      /encounter-card-match-rationale-chip[\s\S]{0,400}fontSize:\s*"0\.65rem"/,
    );
  });
});
