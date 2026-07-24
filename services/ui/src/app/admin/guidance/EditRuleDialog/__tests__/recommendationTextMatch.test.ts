/**
 * Unit tests for the fuzzy text matcher that anchors a leaf's term
 * onto the guideline's own verbatim sentence -- the highlight-to-build
 * wizard's highest-risk pure-function logic.
 *
 * Fixtures: NG12 1.2.8 (single-criterion) and NG12 1.2.9 (six-pathway
 * split), matching the exact wording already used elsewhere in this
 * test suite (EditRuleDialog.test.tsx, SentenceEditor.layout.test.tsx,
 * the plan's wireframes doc).
 */
import {
  computeTextSegments,
  findBestTextMatch,
  findBestTextMatchForCriterion,
  MIN_TOKEN_OVERLAP_SCORE,
} from "../SentenceEditor/recommendationTextMatch";

const NG12_1_2_8 =
  "1.2.8 Consider non-urgent, direct access upper gastrointestinal endoscopy to assess for stomach cancer in people with haematemesis. [2015]";

const NG12_1_2_9 =
  "1.2.9 Consider non-urgent, direct access upper gastrointestinal endoscopy " +
  "to assess for stomach cancer in people aged 55 or over with: " +
  "upper abdominal pain, or " +
  "indigestion with any of the following: upper abdominal pain, nausea, " +
  "vomiting or weight loss, or " +
  "upper abdominal pain and a low haemoglobin level, with any of the " +
  "following: weight loss, heartburn or indigestion, or " +
  "a raised platelet count with any of the following: nausea, vomiting, " +
  "weight loss, heartburn, indigestion or upper abdominal pain, or " +
  "vomiting with any of the following: weight loss, heartburn or " +
  "indigestion, or " +
  "nausea with any of the following: weight loss, heartburn or " +
  "indigestion. [2015]";

describe("findBestTextMatch: exact path", () => {
  it("finds a plain substring case-insensitively", () => {
    const m = findBestTextMatch(NG12_1_2_8, "haematemesis");
    expect(m).not.toBeNull();
    expect(m!.strategy).toBe("exact");
    expect(m!.score).toBe(1);
    expect(NG12_1_2_8.slice(m!.start, m!.end).toLowerCase()).toBe(
      "haematemesis",
    );
  });

  it("matches regardless of the candidate's own casing", () => {
    const m = findBestTextMatch(NG12_1_2_8, "HAEMATEMESIS");
    expect(m).not.toBeNull();
    expect(m!.strategy).toBe("exact");
  });

  it("finds 'aged 55 or over' verbatim in the 1.2.9 sentence", () => {
    const m = findBestTextMatch(NG12_1_2_9, "aged 55 or over");
    expect(m).not.toBeNull();
    expect(m!.strategy).toBe("exact");
    expect(m!.matchedText.toLowerCase()).toBe("aged 55 or over");
  });

  it("finds each pathway's leaf phrase in the 1.2.9 sentence", () => {
    for (const phrase of [
      "upper abdominal pain",
      "indigestion",
      "nausea",
      "vomiting",
      "weight loss",
      "heartburn",
      "a raised platelet count",
    ]) {
      const m = findBestTextMatch(NG12_1_2_9, phrase);
      expect(m).not.toBeNull();
      expect(m!.strategy).toBe("exact");
    }
  });

  it("collapses internal whitespace differences between candidate and text", () => {
    const m = findBestTextMatch(NG12_1_2_8, "  haematemesis  ");
    expect(m).not.toBeNull();
  });

  it("returns null when text or candidate is missing", () => {
    expect(findBestTextMatch(null, "haematemesis")).toBeNull();
    expect(findBestTextMatch(NG12_1_2_8, "")).toBeNull();
    expect(findBestTextMatch(undefined, undefined)).toBeNull();
  });
});

describe("findBestTextMatch: token-overlap fallback", () => {
  it("matches a clinical synonym via shared tokens (heartburn vs acid reflux (heartburn))", () => {
    const m = findBestTextMatch(NG12_1_2_9, "acid reflux (heartburn)");
    expect(m).not.toBeNull();
    // "heartburn" appears verbatim in the guideline text and shares a
    // token with the candidate, so this clears the overlap floor even
    // though the exact phrase "acid reflux (heartburn)" does not
    // appear in NG12 1.2.9's wording.
    expect(m!.score).toBeGreaterThanOrEqual(MIN_TOKEN_OVERLAP_SCORE);
  });

  it("matches a near-miss phrase ('weight decreased' vs 'weight loss')", () => {
    const m = findBestTextMatch(NG12_1_2_9, "weight decreased");
    expect(m).not.toBeNull();
    expect(m!.matchedText.toLowerCase()).toContain("weight");
  });

  it("returns null for a phrase with no meaningful token overlap", () => {
    const m = findBestTextMatch(NG12_1_2_9, "acute appendicitis");
    expect(m).toBeNull();
  });

  it("does not let stopwords alone drive a false-positive match", () => {
    // Every token in this candidate is a stopword, so there is nothing
    // left to score against once stopwords are excluded, even though
    // the reordering means it is not an exact substring either.
    const m = findBestTextMatch(NG12_1_2_9, "the of with any");
    expect(m).toBeNull();
  });
});

describe("findBestTextMatchForCriterion", () => {
  it("prefers preferred_term over term when both are supplied", () => {
    const m = findBestTextMatchForCriterion(NG12_1_2_8, {
      preferred_term: "Haematemesis (disorder)",
      term: "some unrelated query",
    });
    expect(m).not.toBeNull();
    expect(m!.matchedText.toLowerCase()).toBe("haematemesis");
  });

  it("falls back to term when preferred_term does not match", () => {
    const m = findBestTextMatchForCriterion(NG12_1_2_8, {
      preferred_term: "totally unrelated finding",
      term: "haematemesis",
    });
    expect(m).not.toBeNull();
  });

  it("returns null for a criterion with neither field set", () => {
    expect(findBestTextMatchForCriterion(NG12_1_2_8, {})).toBeNull();
    expect(findBestTextMatchForCriterion(NG12_1_2_8, null)).toBeNull();
  });
});

describe("computeTextSegments", () => {
  it("splits text into matched/unmatched segments in order", () => {
    const range = findBestTextMatch(NG12_1_2_8, "haematemesis")!;
    const segments = computeTextSegments(NG12_1_2_8, [range]);
    expect(segments.length).toBeGreaterThanOrEqual(2);
    const joined = segments.map((s) => s.text).join("");
    expect(joined).toBe(NG12_1_2_8);
    const matchedSegment = segments.find((s) => s.range !== null);
    expect(matchedSegment!.text.toLowerCase()).toBe("haematemesis");
  });

  it("returns a single unmatched segment when there are no ranges", () => {
    const segments = computeTextSegments(NG12_1_2_8, []);
    expect(segments).toHaveLength(1);
    expect(segments[0].range).toBeNull();
    expect(segments[0].text).toBe(NG12_1_2_8);
  });

  it("handles multiple non-overlapping ranges across the 1.2.9 sentence", () => {
    const age = findBestTextMatch(NG12_1_2_9, "aged 55 or over")!;
    const pain = findBestTextMatch(NG12_1_2_9, "a raised platelet count")!;
    const segments = computeTextSegments(NG12_1_2_9, [pain, age]);
    const joined = segments.map((s) => s.text).join("");
    expect(joined).toBe(NG12_1_2_9);
    // Segments come out in document order regardless of input order.
    const matchedTexts = segments
      .filter((s) => s.range !== null)
      .map((s) => s.text.toLowerCase());
    expect(matchedTexts).toEqual(["aged 55 or over", "a raised platelet count"]);
  });

  it("skips a range that overlaps one already placed", () => {
    const whole = { start: 0, end: 20, matchedText: NG12_1_2_8.slice(0, 20), strategy: "exact" as const, score: 1 };
    const overlapping = { start: 5, end: 25, matchedText: NG12_1_2_8.slice(5, 25), strategy: "exact" as const, score: 1 };
    const segments = computeTextSegments(NG12_1_2_8, [whole, overlapping]);
    const joined = segments.map((s) => s.text).join("");
    expect(joined).toBe(NG12_1_2_8);
  });
});
