/**
 * Unit tests for pathwayCopyAcross -- detecting when two pathways in
 * the same rule ask about the exact same findings (NG12 1.2.9's
 * pathway C and D both need nausea/vomiting/weight loss/reflux/
 * dyspepsia/upper abdominal pain, split differently into a lead-or
 * cluster plus a trailing cluster), and building the plan to copy an
 * earlier, already-resolved pathway's SNOMED codes onto a later
 * pathway's matching rows.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import {
  buildCopyAcrossPlan,
  cloneCriterionForCopy,
  findCopyAcrossSource,
  pathwayClusterSignature,
} from "../HighlightWizard/pathwayCopyAcross";
import type { EditableLogicNode, LogicCriterion } from "../types";
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";

const PATHWAY_C_TEXT =
  "raised platelet count with any of the following: nausea, vomiting, " +
  "weight loss, reflux, dyspepsia, upper abdominal pain.";
const PATHWAY_D_TEXT =
  "nausea or vomiting with any of the following: weight loss, reflux, " +
  "dyspepsia, upper abdominal pain.";
const FULL_TEXT = `${PATHWAY_C_TEXT} ${PATHWAY_D_TEXT}`;

const BOUNDARY_C: PathwayTextBoundary = {
  text: PATHWAY_C_TEXT,
  start: 0,
  end: PATHWAY_C_TEXT.length,
  source: "heuristic",
};
const BOUNDARY_D: PathwayTextBoundary = {
  text: PATHWAY_D_TEXT,
  start: FULL_TEXT.indexOf(PATHWAY_D_TEXT),
  end: FULL_TEXT.indexOf(PATHWAY_D_TEXT) + PATHWAY_D_TEXT.length,
  source: "heuristic",
};
const BOUNDARIES = [BOUNDARY_C, BOUNDARY_D];

function concept(id: string, term: string): EditableLogicNode {
  return { node_id: `n-${id}`, kind: "CONCEPT", criterion: { snomed_concept_id: id, preferred_term: term } };
}

function pathwayCNode(): EditableLogicNode {
  return {
    node_id: "pw-c",
    kind: "AND",
    pathway_key: "pw_c",
    children: [
      concept("plt", "Raised platelet count"),
      {
        node_id: "cluster-c",
        kind: "AT_LEAST",
        min: 1,
        cluster_role: "trailing",
        children: [
          concept("n1", "Nausea"),
          concept("n2", "Vomiting"),
          concept("n3", "Weight loss"),
          concept("n4", "Reflux"),
          concept("n5", "Dyspepsia"),
          concept("n6", "Upper abdominal pain"),
        ],
      },
    ],
  };
}

describe("pathwayClusterSignature", () => {
  it("returns the same signature for pathway C and D despite the different lead/trailing split", () => {
    expect(pathwayClusterSignature(BOUNDARY_C)).toBe(pathwayClusterSignature(BOUNDARY_D));
    expect(pathwayClusterSignature(BOUNDARY_C)).toEqual(expect.any(String));
  });

  it("returns null for a plain pathway with no cluster", () => {
    const boundary: PathwayTextBoundary = {
      text: "upper abdominal pain",
      start: 0,
      end: 21,
      source: "heuristic",
    };
    expect(pathwayClusterSignature(boundary)).toBeNull();
  });

  it("does not collide two different clusters that happen to be the same size", () => {
    const boundary: PathwayTextBoundary = {
      text: "nausea with any of the following: vomiting, weight loss",
      start: 0,
      end: 57,
      source: "heuristic",
    };
    const other: PathwayTextBoundary = {
      text: "reflux with any of the following: dyspepsia, heartburn",
      start: 100,
      end: 156,
      source: "heuristic",
    };
    expect(pathwayClusterSignature(boundary)).not.toBe(pathwayClusterSignature(other));
  });
});

describe("findCopyAcrossSource", () => {
  it("finds the earlier pathway with the identical finding set", () => {
    expect(findCopyAcrossSource(BOUNDARIES, 1)).toBe(0);
  });

  it("returns null for the first pathway -- nothing earlier to copy from", () => {
    expect(findCopyAcrossSource(BOUNDARIES, 0)).toBeNull();
  });

  it("returns null when no earlier pathway shares the same findings", () => {
    const unrelated: PathwayTextBoundary = {
      text: "unexplained haematemesis",
      start: 500,
      end: 525,
      source: "heuristic",
    };
    expect(findCopyAcrossSource([unrelated, BOUNDARY_D], 1)).toBeNull();
  });
});

describe("cloneCriterionForCopy", () => {
  it("strips AI-confidence and human-review provenance so a copied leaf starts clean", () => {
    const source: LogicCriterion = {
      snomed_concept_id: "1",
      preferred_term: "Nausea",
      confidence: 0.92,
      needs_human_review: true,
      human_reviewed_at: "2026-01-01T00:00:00Z",
      human_reviewed_by: "dr.smith",
      seeds: [
        { snomed_concept_id: "1", preferred_term: "Nausea", include_descendants: true, distance_child: 2 },
      ],
    };
    const cloned = cloneCriterionForCopy(source);
    expect(cloned.confidence).toBeUndefined();
    expect(cloned.needs_human_review).toBeUndefined();
    expect(cloned.human_reviewed_at).toBeUndefined();
    expect(cloned.human_reviewed_by).toBeUndefined();
    expect(cloned.snomed_concept_id).toBe("1");
    expect(cloned.seeds).toEqual(source.seeds);
    expect(cloned.seeds).not.toBe(source.seeds);
  });
});

describe("buildCopyAcrossPlan", () => {
  it("matches every one of pathway D's rows onto pathway C's already-resolved codes", () => {
    const plan = buildCopyAcrossPlan({
      boundaries: BOUNDARIES,
      targetIndex: 1,
      sourcePathwayNode: pathwayCNode(),
      recommendationText: FULL_TEXT,
      sourceGrouping: "AT_LEAST",
    });

    expect(plan).not.toBeNull();
    expect(plan?.sourceIndex).toBe(0);
    expect(plan?.matches).toHaveLength(6);

    const byText = new Map(plan!.matches.map((m) => [m.item.text.toLowerCase(), m]));
    expect(byText.get("nausea")?.role).toBe("lead");
    expect(byText.get("vomiting")?.role).toBe("lead");
    expect(byText.get("weight loss")?.role).toBe("trailing");
    expect(byText.get("nausea")?.criterion.snomed_concept_id).toBe("n1");
    expect(byText.get("upper abdominal pain")?.criterion.snomed_concept_id).toBe("n6");

    // The source's grouping choice is offered as the starting default
    // for BOTH of the target's clusters -- never applied silently,
    // just pre-filled (see StepPathwayConditions' "Change" action).
    expect(plan?.groupingToApply).toBe("AT_LEAST");
    expect(plan?.leadGroupingToApply).toBe("AT_LEAST");
  });

  it("strips confidence/review fields from every copied criterion", () => {
    const scored = pathwayCNode();
    const cluster = scored.children!.find((c) => c.node_id === "cluster-c")!;
    cluster.children = cluster.children!.map((leaf) => ({
      ...leaf,
      criterion: { ...leaf.criterion!, confidence: 0.4, needs_human_review: true },
    }));

    const plan = buildCopyAcrossPlan({
      boundaries: BOUNDARIES,
      targetIndex: 1,
      sourcePathwayNode: scored,
      recommendationText: FULL_TEXT,
    });

    expect(plan?.matches.length).toBeGreaterThan(0);
    for (const match of plan?.matches ?? []) {
      expect(match.criterion.confidence).toBeUndefined();
      expect(match.criterion.needs_human_review).toBeUndefined();
    }
  });

  it("returns null when there is no duplicate pathway to copy from", () => {
    const plan = buildCopyAcrossPlan({
      boundaries: [BOUNDARY_C],
      targetIndex: 0,
      sourcePathwayNode: pathwayCNode(),
      recommendationText: PATHWAY_C_TEXT,
    });
    expect(plan).toBeNull();
  });

  it("returns null when the source pathway has nothing resolved yet", () => {
    const unresolvedSource: EditableLogicNode = {
      node_id: "pw-c",
      kind: "AND",
      pathway_key: "pw_c",
      children: [],
    };
    const plan = buildCopyAcrossPlan({
      boundaries: BOUNDARIES,
      targetIndex: 1,
      sourcePathwayNode: unresolvedSource,
      recommendationText: FULL_TEXT,
    });
    expect(plan).toBeNull();
  });
});
