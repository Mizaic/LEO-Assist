/**
 * Shared stress-test fixture: NG12 1.2.9 (upper GI endoscopy referral).
 *
 * > "Consider non-urgent, direct access upper gastrointestinal
 * > endoscopy... in people aged 55 or over with: treatment-resistant
 * > dyspepsia, or upper abdominal pain with low haemoglobin levels, or
 * > raised platelet count with any of the following: nausea, vomiting,
 * > weight loss, reflux, dyspepsia, upper abdominal pain, or nausea or
 * > vomiting with any of the following: weight loss, reflux, dyspepsia,
 * > upper abdominal pain."
 *
 * Coded as `AND[DEMOGRAPHIC(age>=55), OR[6 pathways]]`: a demographic
 * prerequisite wrapping an OR of six pathways, several of which mix a
 * plain CONCEPT leaf with an advanced-mode OBSERVATION leaf plus a
 * nested "any of these" AT_LEAST cluster. This is the worst-case shape
 * that motivated extracting a single shared `isPathwaySplit()` --
 * see EditRuleDialog/pathwayDetection.ts.
 *
 * Reused by:
 *  - pathwayDetection.test.ts (does the OR at depth 1 get detected?)
 *  - LogicTreeEditor.layout.test.tsx (does the Advanced view render
 *    6 lettered pathway cards, not one nested blob?)
 *  - SentenceEditor.layout.test.tsx (does the Simple prose view match
 *    the validated wireframe?)
 */
import { assignNodeIds, type LogicNodeSeed } from "../../treeOps";
import type { EditableLogicNode } from "../../types";

function concept(term: string, snomedId: string): LogicNodeSeed {
  return {
    kind: "CONCEPT",
    criterion: { snomed_concept_id: snomedId, preferred_term: term },
  };
}

function anyOfCluster(items: Array<[string, string]>): LogicNodeSeed {
  return {
    kind: "AT_LEAST",
    min: 1,
    children: items.map(([term, snomedId]) => concept(term, snomedId)),
  };
}

function referenceRangeObservation(
  term: string,
  observableId: string,
  bound: "upper" | "lower",
): LogicNodeSeed {
  return {
    kind: "OBSERVATION",
    observation: {
      observable_id: observableId,
      observable_term: term,
      operator: bound === "lower" ? "<" : ">",
      value: 0,
      unit: "",
      reference_range: { bound },
    },
  };
}

const COMMON_CLUSTER: Array<[string, string]> = [
  ["weight decreased", "89362005"],
  ["acid reflux (heartburn)", "266435006"],
  ["indigestion (dyspepsia)", "162076009"],
];

const FULL_SYMPTOM_CLUSTER: Array<[string, string]> = [
  ["nausea", "422587007"],
  ["vomiting", "422400008"],
  ["weight decreased", "89362005"],
  ["acid reflux (heartburn)", "266435006"],
  ["indigestion (dyspepsia)", "162076009"],
  ["upper abdominal pain", "43364001"],
];

/**
 * [A] Patient has upper abdominal pain -- a single-condition pathway.
 *
 * Wrapped in a 1-child AND (rather than a bare CONCEPT leaf) because
 * every pathway in the compiled tree is its own group node, even when
 * it only has one condition -- this is also what PathwayCard.tsx
 * (Advanced view) requires: it only renders group-kind pathway
 * children, matching how the real rule compiler shapes pathways.
 */
const pathwayA: LogicNodeSeed = {
  kind: "AND",
  children: [concept("upper abdominal pain", "43364001")],
};

/** [B] Indigestion, and any of: upper abdominal pain, nausea, vomiting, weight decreased. */
const pathwayB: LogicNodeSeed = {
  kind: "AND",
  children: [
    concept("indigestion (dyspepsia)", "162076009"),
    anyOfCluster([
      ["upper abdominal pain", "43364001"],
      ["nausea", "422587007"],
      ["vomiting", "422400008"],
      ["weight decreased", "89362005"],
    ]),
  ],
};

/** [C] Upper abdominal pain + low haemoglobin, and any of the common cluster. */
const pathwayC: LogicNodeSeed = {
  kind: "AND",
  children: [
    concept("upper abdominal pain", "43364001"),
    referenceRangeObservation("hemoglobin", "718-7", "lower"),
    anyOfCluster(COMMON_CLUSTER),
  ],
};

/** [D] Mirrors C with a raised platelet count instead of low haemoglobin. */
const pathwayD: LogicNodeSeed = {
  kind: "AND",
  children: [
    referenceRangeObservation("platelet count", "777-3", "upper"),
    anyOfCluster(FULL_SYMPTOM_CLUSTER),
  ],
};

/** [E] Vomiting, and any of: weight loss, reflux, dyspepsia, upper abdominal pain. */
const pathwayE: LogicNodeSeed = {
  kind: "AND",
  children: [
    concept("vomiting", "422400008"),
    anyOfCluster(COMMON_CLUSTER),
  ],
};

/** [F] Nausea, and any of: weight loss, reflux, dyspepsia, upper abdominal pain. */
const pathwayF: LogicNodeSeed = {
  kind: "AND",
  children: [
    concept("nausea", "422587007"),
    anyOfCluster(COMMON_CLUSTER),
  ],
};

const NG12_1_2_9_SEED: LogicNodeSeed = {
  kind: "AND",
  children: [
    { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 55, unit: "years" },
    { kind: "OR", children: [pathwayA, pathwayB, pathwayC, pathwayD, pathwayE, pathwayF] },
  ],
};

/** Fresh, fully node-id'd copy of the NG12 1.2.9 tree for each caller. */
export function makeNg12129Tree(): EditableLogicNode {
  return assignNodeIds(NG12_1_2_9_SEED);
}
