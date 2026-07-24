/**
 * Unit tests for the text-only pathway-boundary heuristic (Step 2
 * fallback path, used when no `recommendation_structure` exists).
 *
 * NG12 1.2.9 is the canonical fixture for the six-pathway (A-F) case;
 * a small local-guideline-style sentence covers the simpler heuristic
 * fallback path with no nested "any of the following" lists.
 */
import {
  detectAtLeastCluster,
  looksLikePathwaySplit,
  resolveAtLeastCluster,
  splitPathways,
  splitPathwaysByOrHeuristic,
} from "../SentenceEditor/pathwayTextSplit";
import type { RecommendationStructure, RecommendationStructureItem } from "../SentenceEditor/pathwayTextSplit";

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

describe("splitPathwaysByOrHeuristic", () => {
  it("splits NG12 1.2.9 into exactly six pathway segments (A-F)", () => {
    const boundaries = splitPathwaysByOrHeuristic(NG12_1_2_9);
    expect(boundaries).not.toBeNull();
    expect(boundaries).toHaveLength(6);

    const joined = boundaries!.map((b) => b.text).join("");
    expect(joined).toBe(NG12_1_2_9);
  });

  it("does not split inside a nested 'any of the following: a, b or c' list", () => {
    const boundaries = splitPathwaysByOrHeuristic(NG12_1_2_9)!;
    // Pathway B's segment must contain its whole nested list intact --
    // "vomiting or weight loss" must not itself be split into two rows.
    const pathwayB = boundaries[1].text;
    expect(pathwayB).toContain("any of the following");
    expect(pathwayB).toContain("vomiting or weight loss");
  });

  it("each segment maps to the expected leaf phrase", () => {
    const boundaries = splitPathwaysByOrHeuristic(NG12_1_2_9)!;
    expect(boundaries[0].text).toContain("upper abdominal pain");
    expect(boundaries[1].text.toLowerCase()).toContain("indigestion");
    expect(boundaries[2].text.toLowerCase()).toContain("haemoglobin");
    expect(boundaries[3].text.toLowerCase()).toContain("platelet count");
    expect(boundaries[4].text.toLowerCase()).toContain("vomiting");
    expect(boundaries[5].text.toLowerCase()).toContain("nausea");
  });

  it("returns contiguous, non-overlapping offsets that reconstruct the text", () => {
    const boundaries = splitPathwaysByOrHeuristic(NG12_1_2_9)!;
    let cursor = 0;
    for (const b of boundaries) {
      expect(b.start).toBe(cursor);
      expect(NG12_1_2_9.slice(b.start, b.end)).toBe(b.text);
      cursor = b.end;
    }
    expect(cursor).toBe(NG12_1_2_9.length);
  });

  it("splits a simple local-guideline sentence with no nested lists", () => {
    const local =
      "Refer urgently if the patient has chest pain, or shortness of breath, or a new fever.";
    const boundaries = splitPathwaysByOrHeuristic(local);
    expect(boundaries).not.toBeNull();
    expect(boundaries).toHaveLength(3);
    expect(boundaries![0].text).toContain("chest pain");
    expect(boundaries![1].text).toContain("shortness of breath");
    expect(boundaries![2].text).toContain("new fever");
  });

  it("returns null for a single-pathway sentence with no top-level 'or'", () => {
    const single =
      "1.2.8 Consider non-urgent, direct access upper gastrointestinal endoscopy to assess for stomach cancer in people with haematemesis. [2015]";
    expect(splitPathwaysByOrHeuristic(single)).toBeNull();
  });

  it("returns null for empty or missing text", () => {
    expect(splitPathwaysByOrHeuristic("")).toBeNull();
    expect(splitPathwaysByOrHeuristic(null)).toBeNull();
    expect(splitPathwaysByOrHeuristic(undefined)).toBeNull();
    expect(splitPathwaysByOrHeuristic("   ")).toBeNull();
  });

  it("does not treat a bare 'or' with no preceding comma as a boundary", () => {
    // "55 or over" must never be treated as a pathway split point.
    const boundaries = splitPathwaysByOrHeuristic(
      "In people aged 55 or over with X, or Y.",
    );
    expect(boundaries).toHaveLength(2);
    expect(boundaries![0].text).toContain("55 or over");
  });
});

describe("looksLikePathwaySplit", () => {
  it("agrees with splitPathwaysByOrHeuristic", () => {
    expect(looksLikePathwaySplit(NG12_1_2_9)).toBe(true);
    expect(looksLikePathwaySplit("no split here at all")).toBe(false);
  });
});

describe("detectAtLeastCluster", () => {
  it("splits pathway B into a lead condition and 4 AT_LEAST items", () => {
    const boundaries = splitPathwaysByOrHeuristic(NG12_1_2_9)!;
    const cluster = detectAtLeastCluster(boundaries[1].text);
    expect(cluster).not.toBeNull();
    expect(cluster!.leadText.toLowerCase()).toContain("indigestion");
    expect(cluster!.items.map((i) => i.toLowerCase())).toEqual([
      "upper abdominal pain",
      "nausea",
      "vomiting",
      "weight loss",
    ]);
  });

  it("strips a trailing citation year from the last item", () => {
    const boundaries = splitPathwaysByOrHeuristic(NG12_1_2_9)!;
    const cluster = detectAtLeastCluster(boundaries[5].text);
    expect(cluster).not.toBeNull();
    expect(cluster!.items[cluster!.items.length - 1]).not.toMatch(/\[2015\]/);
  });

  it("returns null when there is no 'any of the following' marker", () => {
    expect(detectAtLeastCluster("upper abdominal pain")).toBeNull();
  });

  it("returns an empty leadText when the marker starts the segment", () => {
    const cluster = detectAtLeastCluster(
      "any of the following: nausea, vomiting or weight loss",
    );
    expect(cluster).not.toBeNull();
    expect(cluster!.leadText).toBe("");
    expect(cluster!.items).toEqual(["nausea", "vomiting", "weight loss"]);
  });
});

/**
 * Builds an offset-consistent `RecommendationStructure` fixture the
 * same way the (upstream) HTML list-tree parser would: appending each
 * piece of text to a running string and recording start/end against
 * THAT running length, so there is no risk of the fixture's own
 * offsets drifting out of alignment with its own text -- exactly the
 * "positionally aligned with verbatim" guarantee the real parser
 * must provide (see the plan's "Ingestion" section).
 */
function buildNg129StructureFixture(): {
  text: string;
  structure: RecommendationStructure;
} {
  let text = "";
  const append = (s: string) => {
    text += s;
  };
  const takeItem = (
    ownText: string,
    childTexts: string[] = [],
  ): RecommendationStructureItem => {
    const start = text.length;
    append(ownText);
    const end = text.length;
    if (childTexts.length === 0) return { text: ownText, start, end };
    append(" with any of the following: ");
    const children = childTexts.map((childText, i) => {
      const cStart = text.length;
      append(childText);
      const cEnd = text.length;
      if (i < childTexts.length - 1) {
        append(i === childTexts.length - 2 ? " or " : ", ");
      }
      return { text: childText, start: cStart, end: cEnd };
    });
    return { text: ownText, start, end, children };
  };

  const lead_text =
    "1.2.9 Consider non-urgent, direct access upper gastrointestinal " +
    "endoscopy to assess for stomach cancer in people aged 55 or over with: ";
  append(lead_text);

  const items: RecommendationStructureItem[] = [];
  items.push(takeItem("upper abdominal pain"));
  append(", or ");
  items.push(
    takeItem("indigestion", ["upper abdominal pain", "nausea", "vomiting", "weight loss"]),
  );
  append(", or ");
  items.push(
    takeItem("upper abdominal pain and a low haemoglobin level", [
      "weight loss",
      "heartburn",
      "indigestion",
    ]),
  );
  append(", or ");
  items.push(
    takeItem("a raised platelet count", [
      "nausea",
      "vomiting",
      "weight loss",
      "heartburn",
      "indigestion",
      "upper abdominal pain",
    ]),
  );
  append(", or ");
  items.push(takeItem("vomiting", ["weight loss", "heartburn", "indigestion"]));
  append(", or ");
  items.push(takeItem("nausea", ["weight loss", "heartburn", "indigestion"]));
  const trailing_text = ". [2015]";
  append(trailing_text);

  return { text, structure: { lead_text, items, trailing_text } };
}

describe("splitPathways (structure-first)", () => {
  it("prefers the structured tree over the text heuristic when both are available", () => {
    const { text, structure } = buildNg129StructureFixture();
    const boundaries = splitPathways(text, structure);
    expect(boundaries).not.toBeNull();
    expect(boundaries).toHaveLength(6);
    expect(boundaries!.every((b) => b.source === "structure")).toBe(true);
  });

  it("each structural boundary's offsets round-trip against the source text", () => {
    const { text, structure } = buildNg129StructureFixture();
    const boundaries = splitPathways(text, structure)!;
    for (const b of boundaries) {
      expect(text.slice(b.start, b.end)).toBe(b.text);
    }
  });

  it("carries the nested list through as structureChildren, not re-parsed text", () => {
    const { text, structure } = buildNg129StructureFixture();
    const boundaries = splitPathways(text, structure)!;
    const pathwayB = boundaries[1];
    expect(pathwayB.text).toBe("indigestion");
    expect(pathwayB.structureChildren?.map((c) => c.text)).toEqual([
      "upper abdominal pain",
      "nausea",
      "vomiting",
      "weight loss",
    ]);
    // Pathway A has no nested list -- no structureChildren at all.
    expect(boundaries[0].structureChildren).toBeUndefined();
  });

  it("falls back to the text heuristic when no structure is supplied", () => {
    const { text } = buildNg129StructureFixture();
    const boundaries = splitPathways(text, null);
    expect(boundaries).not.toBeNull();
    expect(boundaries!.every((b) => b.source === "heuristic")).toBe(true);
    // The heuristic path re-derives the same six pathways from the flat
    // text alone -- same count, no structure needed to get there.
    expect(boundaries).toHaveLength(6);
  });

  it("falls back to the text heuristic when structure has fewer than 2 items", () => {
    const local = "Refer urgently if the patient has chest pain, or shortness of breath.";
    const flatStructure: RecommendationStructure = {
      lead_text: local,
      items: [{ text: local, start: 0, end: local.length }],
    };
    const boundaries = splitPathways(local, flatStructure);
    expect(boundaries).not.toBeNull();
    expect(boundaries!.every((b) => b.source === "heuristic")).toBe(true);
  });

  it("looksLikePathwaySplit agrees with splitPathways for both paths", () => {
    const { text, structure } = buildNg129StructureFixture();
    expect(looksLikePathwaySplit(text, structure)).toBe(true);
    expect(looksLikePathwaySplit(text, null)).toBe(true);
    expect(looksLikePathwaySplit("no split here at all", null)).toBe(false);
  });
});

describe("resolveAtLeastCluster", () => {
  it("uses structureChildren directly when source is 'structure', skipping text parsing", () => {
    const { text, structure } = buildNg129StructureFixture();
    const pathwayB = splitPathways(text, structure)![1];
    const cluster = resolveAtLeastCluster(pathwayB);
    expect(cluster).toEqual({
      leadText: "indigestion",
      items: ["upper abdominal pain", "nausea", "vomiting", "weight loss"],
    });
  });

  it("returns null when a structural boundary has no nested children", () => {
    const { text, structure } = buildNg129StructureFixture();
    const pathwayA = splitPathways(text, structure)![0];
    expect(resolveAtLeastCluster(pathwayA)).toBeNull();
  });

  it("falls back to the text heuristic for a 'heuristic' source boundary", () => {
    const boundary = {
      text: "indigestion with any of the following: nausea, vomiting or weight loss",
      source: "heuristic" as const,
    };
    const cluster = resolveAtLeastCluster(boundary);
    expect(cluster).not.toBeNull();
    expect(cluster!.leadText).toBe("indigestion");
    expect(cluster!.items).toEqual(["nausea", "vomiting", "weight loss"]);
  });
});
