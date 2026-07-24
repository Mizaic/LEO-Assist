/**
 * NG12 1.2.9 stacked-wizard regression: the four situations confirmed
 * in Step 2 (structure/heuristic left column), their Step 3 row
 * shapes, OR rebuild when an AI draft has six pathways, and quote-
 * panel windows that keep nested-list wording off Situation A.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { scopeHighlightsToActiveSituation } from "../GuidelineQuotePanel";
import {
  buildPathwayRows,
  materializePathways,
  pathwayTextWindow,
} from "../HighlightWizard/wizardMapping";
import type { EditableLogicNode, NodeUpdate } from "../types";
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import type { HighlightSpan } from "../SentenceEditor/HighlightableRecommendationText";

/** Synthetic flattened text matching the real 4-situation NG12 1.2.9
 *  shape the wizard's Step 2 left column already shows correctly. */
function buildNg129FourSituationFixture(): {
  text: string;
  boundaries: PathwayTextBoundary[];
} {
  const lead =
    "Consider endoscopy in people aged 55 or over with ";
  const a = "treatment-resistant dyspepsia";
  const b = "upper abdominal pain with low haemoglobin levels";
  const cLead = "a raised platelet count with any of the following:";
  const cItems = [
    "nausea",
    "vomiting",
    "weight loss",
    "reflux",
    "dyspepsia",
    "upper abdominal pain",
  ];
  const dLead = "nausea or vomiting with any of the following:";
  const dItems = ["weight loss", "reflux", "dyspepsia", "upper abdominal pain"];

  let text = lead;
  const boundaries: PathwayTextBoundary[] = [];

  const pushPlain = (own: string) => {
    const start = text.length;
    text += own;
    boundaries.push({
      start,
      end: text.length,
      text: own,
      source: "structure",
    });
  };

  const pushCluster = (own: string, children: string[]) => {
    const start = text.length;
    text += own;
    const end = text.length;
    text += " ";
    const structureChildren = children.map((child, i) => {
      const cStart = text.length;
      text += child;
      const cEnd = text.length;
      if (i < children.length - 1) text += ", ";
      return { text: child, start: cStart, end: cEnd };
    });
    boundaries.push({
      start,
      end,
      text: own,
      source: "structure",
      structureChildren,
    });
  };

  pushPlain(a);
  text += ", or ";
  pushPlain(b);
  text += ", or ";
  pushCluster(cLead, cItems);
  text += ", or ";
  pushCluster(dLead, dItems);
  text += ".";

  return { text, boundaries };
}

describe("NG12 1.2.9 pathway shapes (Step 3 rows)", () => {
  const { boundaries } = buildNg129FourSituationFixture();

  it("A is a single condition row", () => {
    const { items, hasCluster } = buildPathwayRows(boundaries[0]);
    expect(hasCluster).toBe(false);
    expect(items).toHaveLength(1);
    expect(items[0].text).toContain("dyspepsia");
  });

  it("B splits into two AND rows (pain + low haemoglobin)", () => {
    const { items, hasCluster } = buildPathwayRows(boundaries[1]);
    expect(hasCluster).toBe(false);
    expect(items.map((i) => i.text)).toEqual([
      "upper abdominal pain",
      "low haemoglobin levels",
    ]);
  });

  it("C is a lead finding plus a 6-item AT_LEAST cluster", () => {
    const { items, hasCluster } = buildPathwayRows(boundaries[2]);
    expect(hasCluster).toBe(true);
    expect(items).toHaveLength(1);
    expect(items[0].text.toLowerCase()).toContain("platelet");
    expect(items[0].children).toHaveLength(6);
  });

  it("D is a lead-or pair plus a 4-item trailing cluster", () => {
    const { items, hasCluster, leadCluster } = buildPathwayRows(boundaries[3]);
    expect(hasCluster).toBe(true);
    expect(leadCluster?.items.map((i) => i.text)).toEqual(["nausea", "vomiting"]);
    expect(items.map((i) => i.text)).toEqual(
      expect.arrayContaining(["weight loss", "reflux", "dyspepsia", "upper abdominal pain"]),
    );
  });
});

describe("NG12 1.2.9 OR rebuild on Confirm Split", () => {
  it("rebuilds a 6-child AI OR down to exactly 4 empty pathway shells", () => {
    const age: EditableLogicNode = {
      node_id: "age",
      kind: "DEMOGRAPHIC",
      field: "age",
      operator: ">=",
      value: "55",
    };
    const aiPathways = Array.from({ length: 6 }, (_, i) => ({
      node_id: `pw-${i}`,
      kind: "AND" as const,
      pathway_key: `ai_${i}`,
      children: [
        {
          node_id: `c-${i}`,
          kind: "CONCEPT" as const,
          criterion: {
            snomed_concept_id: String(i),
            preferred_term: "Nausea",
          },
        },
      ],
    }));
    const tree: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [age, { node_id: "or", kind: "OR", children: aiPathways }],
    };
    const updates: NodeUpdate[] = [];
    expect(materializePathways(tree, 4, (u) => updates.push(u))).toEqual([]);
    expect(updates).toHaveLength(1);
    if (updates[0].kind !== "replace_root") throw new Error("expected replace_root");
    const or = updates[0].node.children!.find((c) => c.kind === "OR")!;
    expect(or.children).toHaveLength(4);
    expect(updates[0].node.children![0]).toBe(age);
    expect(or.children!.every((c) => (c.children ?? []).length === 0)).toBe(true);
  });
});

describe("NG12 1.2.9 quote-panel scoping", () => {
  it("keeps nested C/D cluster words out of Situation A's highlights", () => {
    const { text, boundaries } = buildNg129FourSituationFixture();
    const nauseaStart = text.indexOf("nausea");
    const nausea: HighlightSpan = {
      start: nauseaStart,
      end: nauseaStart + "nausea".length,
      kind: "confirmed",
    };
    const ageStart = text.indexOf("aged 55");
    const age: HighlightSpan = {
      start: ageStart,
      end: ageStart + "aged 55 or over".length,
      kind: "confirmed",
    };
    const dyspepsiaStart = text.indexOf("treatment-resistant dyspepsia");
    const dyspepsia: HighlightSpan = {
      start: dyspepsiaStart,
      end: dyspepsiaStart + "treatment-resistant dyspepsia".length,
      kind: "confirmed",
    };

    const windowA = pathwayTextWindow(boundaries, 0, text.length)!;
    expect(nauseaStart).toBeGreaterThanOrEqual(windowA.end);

    const scoped = scopeHighlightsToActiveSituation(
      [age, dyspepsia, nausea],
      boundaries,
      0,
      text.length,
    );
    expect(scoped).toEqual([age, dyspepsia]);
  });
});
