/**
 * Unit tests for NG12 1.7.1 weighted checklist peel + expand.
 * Atlas: DI-42246DA7 / DO-F8C56339
 */
import {
  buildWeightedChecklistState,
  NG12_1_7_1_COMPANION,
  peelWeightedChecklistPhrases,
  resolveCompanionPanels,
  withReifiedWeightedChecklist,
} from "../HighlightWizard/weightedChecklist";
import { buildPathwayRows } from "../HighlightWizard/wizardMapping";
import { buildNoSplitBoundary } from "../SentenceEditor/pathwayTextSplit";
import type { EditableLogicNode } from "../types";

const TEXT =
  "1.7.1 Refer people using a suspected cancer pathway referral for melanoma " +
  "if they have a suspicious pigmented skin lesion with a weighted 7-point " +
  "checklist score of 3 or more. [2015]";

describe("peelWeightedChecklistPhrases", () => {
  it("finds lesion and score phrases in NG12 1.7.1", () => {
    const peeled = peelWeightedChecklistPhrases(TEXT);
    expect(peeled.lesion?.text).toMatch(/suspicious pigmented skin lesion/i);
    expect(peeled.score?.text).toMatch(/weighted 7-point checklist score of 3 or more/i);
  });
});

describe("resolveCompanionPanels", () => {
  it("falls back to the static NG12 1.7.1 pack when API panels are empty", () => {
    const panels = resolveCompanionPanels("NG12", TEXT, null);
    expect(panels).toHaveLength(1);
    expect(panels[0]).toEqual(NG12_1_7_1_COMPANION);
  });

  it("prefers API panels when present", () => {
    const api = [{ ...NG12_1_7_1_COMPANION, title: "From API" }];
    expect(resolveCompanionPanels("NG12", TEXT, api)[0]!.title).toBe("From API");
  });
});

describe("buildPathwayRows with weighted checklist", () => {
  it("peels lesion + score before expand", () => {
    const state = buildWeightedChecklistState(TEXT, [NG12_1_7_1_COMPANION], false);
    expect(state).not.toBeNull();
    const boundary = buildNoSplitBoundary(TEXT, null, state);
    const rows = buildPathwayRows(boundary);
    expect(rows.items.map((i) => i.text)).toEqual([
      "suspicious pigmented skin lesion",
      expect.stringMatching(/weighted 7-point checklist score of 3 or more/i),
    ]);
  });

  it("lists all major and minor features after expand", () => {
    const state = buildWeightedChecklistState(TEXT, [NG12_1_7_1_COMPANION], true);
    const boundary = buildNoSplitBoundary(TEXT, null, state);
    const rows = buildPathwayRows(boundary);
    expect(rows.items.map((i) => i.text)).toEqual([
      "suspicious pigmented skin lesion",
      "change in size",
      "irregular shape",
      "irregular colour",
      "largest diameter 7 mm or more",
      "inflammation",
      "oozing",
      "change in sensation",
    ]);
  });
});

describe("withReifiedWeightedChecklist", () => {
  it("builds OR of AT_LEAST(2) majors, AND(1 maj, 1 min), AT_LEAST(3) minors", () => {
    const checklist = buildWeightedChecklistState(TEXT, [NG12_1_7_1_COMPANION], true)!;
    const coded = (term: string, id: string): EditableLogicNode => ({
      node_id: `n-${id}`,
      kind: "CONCEPT",
      source_row_text: term,
      criterion: {
        snomed_concept_id: id,
        preferred_term: term,
        term,
        seeds: [{ snomed_concept_id: id, preferred_term: term }],
      },
    });
    const tree: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [
        coded("suspicious pigmented skin lesion", "lesion"),
        coded("change in size", "m1"),
        coded("irregular shape", "m2"),
        coded("irregular colour", "m3"),
        coded("largest diameter 7 mm or more", "n1"),
        coded("inflammation", "n2"),
        coded("oozing", "n3"),
        coded("change in sensation", "n4"),
      ],
    };
    const next = withReifiedWeightedChecklist(tree, checklist);
    expect(next.kind).toBe("AND");
    const scoreOr = next.children?.find((c) => c.kind === "OR");
    expect(scoreOr).toBeTruthy();
    expect(scoreOr!.children).toHaveLength(3);
    const [twoMaj, majAndMin, threeMin] = scoreOr!.children!;
    expect(twoMaj.kind).toBe("AT_LEAST");
    expect(twoMaj.min).toBe(2);
    expect(twoMaj.children).toHaveLength(3);
    expect(majAndMin.kind).toBe("AND");
    expect(majAndMin.children?.[0]?.kind).toBe("AT_LEAST");
    expect(majAndMin.children?.[0]?.min).toBe(1);
    expect(majAndMin.children?.[1]?.kind).toBe("AT_LEAST");
    expect(majAndMin.children?.[1]?.min).toBe(1);
    expect(threeMin.kind).toBe("AT_LEAST");
    expect(threeMin.min).toBe(3);
    expect(threeMin.children).toHaveLength(4);
    const lesion = next.children?.find(
      (c) =>
        c.kind === "CONCEPT" &&
        /suspicious pigmented skin lesion/i.test(c.source_row_text || ""),
    );
    expect(lesion).toBeTruthy();
  });
});
