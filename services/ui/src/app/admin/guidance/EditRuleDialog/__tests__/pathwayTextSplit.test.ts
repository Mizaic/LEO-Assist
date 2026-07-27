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
  looksLikeLeadOrCluster,
  looksLikePathwaySplit,
  looksLikeWithAnd,
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

  it("splits on a comma-then-or with NO space -- the real NG12 1.2.9 defect", () => {
    // Verified against the live Recommendation node for NG12 1.2.9
    // (NG12:v2:CH002:SEC001:R008): its ingested `verbatim` literally
    // reads "...low haemoglobin levels,or raised platelet count..."
    // with zero whitespace between the comma and "or". A `\s+`
    // requirement here silently drops this boundary and merges two
    // real pathways into one.
    const text =
      "upper abdominal pain with low haemoglobin levels,or raised platelet count " +
      "with any of the following: nausea vomiting.";
    const boundaries = splitPathwaysByOrHeuristic(text);
    expect(boundaries).not.toBeNull();
    expect(boundaries).toHaveLength(2);
    expect(boundaries![0].text).toBe("upper abdominal pain with low haemoglobin levels,or ");
    expect(boundaries![1].text).toBe(
      "raised platelet count with any of the following: nausea vomiting.",
    );
    // Offsets must still reconstruct the original text losslessly.
    expect(boundaries!.map((b) => b.text).join("")).toBe(text);
  });

  it("still splits correctly with the conventional single space before 'or'", () => {
    const text = "chest pain, or shortness of breath.";
    const boundaries = splitPathwaysByOrHeuristic(text);
    expect(boundaries).toHaveLength(2);
    expect(boundaries![0].text).toBe("chest pain, or ");
    expect(boundaries![1].text).toBe("shortness of breath.");
  });

  it("still splits correctly with extra whitespace before 'or'", () => {
    const text = "chest pain,   or shortness of breath.";
    const boundaries = splitPathwaysByOrHeuristic(text);
    expect(boundaries).toHaveLength(2);
    expect(boundaries![0].text).toBe("chest pain,   or ");
    expect(boundaries![1].text).toBe("shortness of breath.");
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

  it("recognises NICE's numeric-quantifier phrasing, not just the word 'any'", () => {
    const cluster = detectAtLeastCluster(
      "if they have 2 or more of the following unexplained symptoms: cough, fatigue, chest pain",
    );
    expect(cluster).not.toBeNull();
    expect(cluster!.leadText).toBe("if they have");
    expect(cluster!.items).toEqual(["cough", "fatigue", "chest pain"]);
  });

  it("recognises a spelled-out quantifier ('one of the following')", () => {
    const cluster = detectAtLeastCluster(
      "one of the following: raised platelet count, thrombocytosis",
    );
    expect(cluster).not.toBeNull();
    expect(cluster!.items).toEqual(["raised platelet count", "thrombocytosis"]);
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
 *
 * `takeItem`'s own text INCLUDES the "with any of the following:"
 * marker phrase when the item has children -- matching
 * `nice_list_parser.py`'s `_own_text`, which only excludes the nested
 * `<ul>` itself, not the marker sentence sitting in the same `<li>`
 * paragraph as that marker. A resolver must strip the marker from
 * this text itself; it is not pre-excluded by the parser.
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
    leadPhrase: string,
    childTexts: string[] = [],
  ): RecommendationStructureItem => {
    const start = text.length;
    const ownText =
      childTexts.length === 0 ? leadPhrase : `${leadPhrase} with any of the following:`;
    append(ownText);
    const end = text.length;
    if (childTexts.length === 0) return { text: ownText, start, end };
    append(" ");
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
    expect(pathwayB.text).toBe("indigestion with any of the following:");
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

/**
 * Real-world regression: NG12 1.10.4 ("Offer the following to assess
 * for myeloma... a full blood count, and blood tests for: calcium,
 * plasma viscosity or erythrocyte sedimentation rate paraprotein,
 * ..."). NICE's markup renders "a full blood count" and "blood tests
 * for: ..." as sibling `<li>` items, but they are joined by "and", not
 * "or" -- this is ONE situation with two things to test for, not two
 * separate situations. Regression for the wizard mis-labelling this
 * as "The guideline lists 2 situations" and offering it as a 2-rule
 * split.
 */
function buildAndJoinedStructureFixture(): {
  text: string;
  structure: RecommendationStructure;
} {
  const lead_text =
    "1.10.4 Offer the following to assess for myeloma in people aged 60 " +
    "and over with persistent bone pain, particularly back pain, or " +
    "unexplained fracture: ";
  let text = lead_text;

  const itemAStart = text.length;
  const itemAText = "a full blood count";
  text += itemAText;
  const itemAEnd = text.length;

  text += ", and ";

  const itemBStart = text.length;
  const itemBText = "blood tests for:";
  text += itemBText;
  const itemBEnd = text.length;
  text += " ";

  const childTexts = [
    "calcium",
    "plasma viscosity or erythrocyte sedimentation rate paraprotein, " +
      "using serum protein electrophoresis free light chains contained in " +
      "serum",
  ];
  const children: RecommendationStructureItem[] = childTexts.map((childText, i) => {
    const cStart = text.length;
    text += childText;
    const cEnd = text.length;
    if (i < childTexts.length - 1) text += ". ";
    return { text: childText, start: cStart, end: cEnd };
  });

  const trailing_text = ". [2015, amended 2025]";
  text += trailing_text;

  const structure: RecommendationStructure = {
    lead_text,
    items: [
      { text: itemAText, start: itemAStart, end: itemAEnd },
      { text: itemBText, start: itemBStart, end: itemBEnd, children },
    ],
    trailing_text,
  };
  return { text, structure };
}

describe("splitPathways ('and'-joined structure is not a situation split)", () => {
  it("does not treat NG12 1.10.4's AND-joined action list as 2 situations", () => {
    const { text, structure } = buildAndJoinedStructureFixture();
    expect(splitPathways(text, structure)).toBeNull();
  });

  it("looksLikePathwaySplit agrees: false for an AND-joined list", () => {
    const { text, structure } = buildAndJoinedStructureFixture();
    expect(looksLikePathwaySplit(text, structure)).toBe(false);
  });

  it("still splits a genuinely OR-joined structure into situations", () => {
    const { text, structure } = buildNg129StructureFixture();
    const boundaries = splitPathways(text, structure);
    expect(boundaries).not.toBeNull();
    expect(boundaries).toHaveLength(6);
  });
});

/**
 * Real-world regression: NG12 1.1.2 ("Offer an urgent, direct access
 * chest X-ray... in people aged 40 and over if they have 2 or more of
 * the following unexplained symptoms, or if they have ever smoked and
 * have 1 or more of the following unexplained symptoms: cough,
 * fatigue, shortness of breath, chest pain, weight loss, appetite
 * loss."). NICE's markup renders the SIX symptoms as one flat `<ul>`
 * shared by both the "2 or more" and "ever smoked + 1 or more" prose
 * clauses -- the guideline's own structure has no opinion on how many
 * SITUATIONS this is (that split lives entirely in the lead-in prose),
 * so treating the six list items as six top-level pathways (A-F) was
 * wrong: the real answer is two.
 */
function buildNg112StructureFixture(): {
  text: string;
  structure: RecommendationStructure;
} {
  let text = "";
  const append = (s: string) => {
    text += s;
  };
  const takeFlatItem = (label: string): RecommendationStructureItem => {
    const start = text.length;
    append(label);
    return { text: label, start, end: text.length };
  };

  const lead_text =
    "Offer an urgent, direct access chest X-ray to assess for lung cancer " +
    "in people aged 40 and over if they have 2 or more of the following " +
    "unexplained symptoms, or if they have ever smoked and have 1 or " +
    "more of the following unexplained symptoms: ";
  append(lead_text);

  const items: RecommendationStructureItem[] = [];
  for (const [i, symptom] of [
    "cough",
    "fatigue",
    "shortness of breath",
    "chest pain",
    "weight loss",
    "appetite loss",
  ].entries()) {
    if (i > 0) append(", ");
    items.push(takeFlatItem(symptom));
  }
  const trailing_text = ". [2015]";
  append(trailing_text);

  return { text, structure: { lead_text, items, trailing_text } };
}

describe("splitPathways (shared quantifier list is not six situations)", () => {
  it("finds NG12 1.1.2's real 2-way split instead of the shared symptom list's 6 items", () => {
    const { text, structure } = buildNg112StructureFixture();
    const boundaries = splitPathways(text, structure);
    expect(boundaries).not.toBeNull();
    expect(boundaries).toHaveLength(2);
    // Falls through to the flat-text heuristic -- the structure's own
    // list gave no useful opinion on the real (prose-level) split.
    expect(boundaries!.every((b) => b.source === "heuristic")).toBe(true);
  });

  it("keeps the '2 or more' and 'ever smoked' clauses on separate sides of the split", () => {
    const { text, structure } = buildNg112StructureFixture();
    const [pathwayA, pathwayB] = splitPathways(text, structure)!;
    expect(pathwayA.text).toContain("2 or more");
    expect(pathwayA.text).not.toContain("ever smoked");
    expect(pathwayB.text).toContain("ever smoked");
    expect(pathwayB.text).toContain("1 or more");
  });

  it("detects pathway B's own AT_LEAST(1) cluster from the numeric 'N or more of the following' marker", () => {
    const { text, structure } = buildNg112StructureFixture();
    const pathwayB = splitPathways(text, structure)![1];
    const cluster = resolveAtLeastCluster(pathwayB);
    expect(cluster).not.toBeNull();
    expect(cluster!.items).toEqual([
      "cough",
      "fatigue",
      "shortness of breath",
      "chest pain",
      "weight loss",
      "appetite loss",
    ]);
  });

  it("still returns the structure's own items when the list has no quantifier lead-in (no regression)", () => {
    const { text, structure } = buildNg129StructureFixture();
    const boundaries = splitPathways(text, structure);
    expect(boundaries).toHaveLength(6);
    expect(boundaries!.every((b) => b.source === "structure")).toBe(true);
  });

  it("NG12 1.1.3: 'any of the following' list is one situation, not five pathways", () => {
    const lead_text =
      "Consider an urgent chest X-ray to assess for lung cancer in people aged 40 and over with any of the following:";
    let text = `1.1.3 ${lead_text} `;
    const items: RecommendationStructureItem[] = [];
    for (const [i, finding] of [
      "persistent or recurrent chest infection",
      "finger clubbing",
      "supraclavicular lymphadenopathy or persistent cervical lymphadenopathy",
      "chest signs consistent with lung cancer",
      "thrombocytosis",
    ].entries()) {
      if (i > 0) text += " ";
      const start = text.length;
      text += finding;
      items.push({ text: finding, start, end: text.length });
    }
    const structure: RecommendationStructure = { lead_text, items };
    expect(splitPathways(text, structure)).toBeNull();
  });

  /**
   * Wording-independent safety net: even if the ingested `lead_text`
   * does not literally contain "of the following" in a form
   * `AT_LEAST_MARKER_RE` recognises (a real ingestion pipeline may
   * phrase or truncate this differently than the fixtures above
   * assume), 2+ structure items sharing a single ", or " heuristic
   * segment is still decisive, wording-independent evidence that they
   * are one shared list, not one-item-per-situation.
   */
  it("still defers to the heuristic split when the shared list has no recognised marker wording at all", () => {
    let text = "";
    const append = (s: string) => {
      text += s;
    };
    const lead_text =
      "Offer an urgent chest X-ray in people aged 40 and over with 2 of these symptoms, " +
      "or if they have ever smoked with 1 of these symptoms: ";
    append(lead_text);
    const items: RecommendationStructureItem[] = [];
    for (const [i, symptom] of ["cough", "fatigue", "chest pain"].entries()) {
      if (i > 0) append(", ");
      const start = text.length;
      append(symptom);
      items.push({ text: symptom, start, end: text.length });
    }
    const structure: RecommendationStructure = { lead_text, items };

    // The marker regex does not match this wording at all.
    expect(splitPathwaysFromStructureForTest(structure)).toBe(false);

    const boundaries = splitPathways(text, structure);
    expect(boundaries).toHaveLength(2);
    expect(boundaries!.every((b) => b.source === "heuristic")).toBe(true);
  });
});

/** Exposes just the marker-regex verdict for the safety-net test above,
 *  without re-implementing or exporting the regex itself. */
function splitPathwaysFromStructureForTest(structure: RecommendationStructure): boolean {
  return /\b(?:with\s+)?(?:any|(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s+or\s+more)?)\s+of\s+the\s+following\b(?:\s+\w+){0,4}:\s*/i.test(
    structure.lead_text ?? "",
  );
}

describe("resolveAtLeastCluster", () => {
  it("strips the marker phrase from a structural item's own text, skipping text re-parsing of the list", () => {
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

  it("detects a marker-less lead-or cluster in a structural item's own text (NG12 1.2.9 pathway D)", () => {
    // Real NG12:v2:CH002:SEC001:R008 backfilled data: the last item's
    // own text is "nausea or vomiting with any of the following:",
    // with the trailing list as its structureChildren.
    const boundary = {
      text: "nausea or vomiting with any of the following:",
      source: "structure" as const,
      structureChildren: [
        { text: "weight loss", start: 0, end: 0 },
        { text: "reflux", start: 0, end: 0 },
        { text: "dyspepsia", start: 0, end: 0 },
        { text: "upper abdominal pain. [2015]", start: 0, end: 0 },
      ],
    };
    const cluster = resolveAtLeastCluster(boundary);
    expect(cluster).toEqual({
      leadText: "",
      leadCluster: ["nausea", "vomiting"],
      items: ["weight loss", "reflux", "dyspepsia", "upper abdominal pain"],
    });
  });

  it("detects a marker-less lead-or cluster on the heuristic path too", () => {
    const boundary = {
      text: "nausea or vomiting with any of the following: weight loss, reflux, dyspepsia, upper abdominal pain. [2015]",
      source: "heuristic" as const,
    };
    const cluster = resolveAtLeastCluster(boundary);
    expect(cluster).toEqual({
      leadText: "",
      leadCluster: ["nausea", "vomiting"],
      items: ["weight loss", "reflux", "dyspepsia", "upper abdominal pain"],
    });
  });
});

describe("looksLikeLeadOrCluster", () => {
  it("recognises a bare two-term lead-or cluster", () => {
    expect(looksLikeLeadOrCluster("nausea or vomiting")).toEqual(["nausea", "vomiting"]);
  });

  it("recognises a three-term comma + bare-or cluster", () => {
    expect(looksLikeLeadOrCluster("nausea, vomiting or dizziness")).toEqual([
      "nausea",
      "vomiting",
      "dizziness",
    ]);
  });

  it("returns null for ordinary prose containing 'or' inside a long clause", () => {
    expect(
      looksLikeLeadOrCluster(
        "abdominal pain or a change in bowel habit that has persisted for six weeks",
      ),
    ).toBeNull();
  });

  it("returns null for 'X or over' age phrasing (a number, not a term)", () => {
    expect(looksLikeLeadOrCluster("people aged 55 or over")).toBeNull();
  });

  it("returns null when there is no 'or' at all", () => {
    expect(looksLikeLeadOrCluster("indigestion")).toBeNull();
  });

  it("returns null for empty text", () => {
    expect(looksLikeLeadOrCluster("")).toBeNull();
  });

  it("returns null for more than 4 alternatives", () => {
    expect(looksLikeLeadOrCluster("a, b, c, d or e")).toBeNull();
  });
});

describe("looksLikeWithAnd", () => {
  it("splits NG12 situation B into two short findings", () => {
    expect(
      looksLikeWithAnd("upper abdominal pain with low haemoglobin levels"),
    ).toEqual(["upper abdominal pain", "low haemoglobin levels"]);
  });

  it("rejects 'with any of the following' (handled by the AT_LEAST path)", () => {
    expect(
      looksLikeWithAnd("raised platelet count with any of the following: nausea"),
    ).toBeNull();
  });

  it("rejects a long clausal 'with' phrase", () => {
    expect(
      looksLikeWithAnd(
        "pain with a change in bowel habit that has persisted for six weeks",
      ),
    ).toBeNull();
  });

  it("splits a short 'nausea and vomiting' clause into two findings", () => {
    expect(looksLikeWithAnd("nausea and vomiting.")).toEqual([
      "nausea",
      "vomiting",
    ]);
  });

  it("does not split age phrasing that uses 'and'", () => {
    expect(looksLikeWithAnd("people aged 55 and over with weight loss")).toBeNull();
  });
});
