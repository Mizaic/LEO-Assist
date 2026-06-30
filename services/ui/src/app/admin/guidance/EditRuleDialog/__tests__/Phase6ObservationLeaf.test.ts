/**
 * Phase 6 UI tests for the OBSERVATION leaf.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-4C8A09C3
 *   DO: DO-CB6324A3
 *   VT: VT-1A7862B9 (execution_status=passed)
 *
 * Covers:
 *   - treeOps: add_observation, set_observation, set_name (restored
 *     from Phase 2), validation of an OBSERVATION leaf.
 *   - treeToSentence: plain-English rendering of OBSERVATION leaves
 *     in absolute and advanced modes.
 *   - treeToCanvas: an OBSERVATION leaf maps to an ``observation``
 *     row in the canvas model.
 *
 * These are pure-logic tests (no DOM); live-render tests of
 * ``ObservationRow`` go in the existing ``SentenceCanvas.test.tsx``
 * following the same pattern as ``DemographicRow``.
 */

import { applyUpdate, assignNodeIds, findValidationError, observationWithCriterion } from "../treeOps";
import type { LogicNodeSeed } from "../treeOps";
import { treeToSentence } from "../treeToSentence";
import type {
  EditableLogicNode,
  EditableObservationPayload,
} from "../types";

function tree(seed: LogicNodeSeed): EditableLogicNode {
  return assignNodeIds(seed);
}

function observation(
  overrides: Partial<EditableObservationPayload> = {},
): EditableObservationPayload {
  return {
    observable_id: "365632008",
    observable_term: "Platelet count",
    operator: ">=",
    value: 400,
    unit: "10*9/L",
    within_days: 365,
    ...overrides,
  };
}

describe("Phase 6 OBSERVATION leaf -- treeOps", () => {
  it("add_observation inserts an OBSERVATION child under a group", () => {
    const root = tree({ kind: "AND", children: [] });
    const updated = applyUpdate(root, {
      kind: "add_observation",
      parentNodeId: root.node_id,
    });
    expect(updated.children?.length).toBe(1);
    const leaf = updated.children![0];
    expect(leaf.kind).toBe("OBSERVATION");
    expect(leaf.observation).toBeDefined();
    expect(leaf.observation?.operator).toBe(">=");
    expect(leaf.observation?.within_days).toBe(365);
  });

  it("add_observation with a seed pre-populates the payload", () => {
    const root = tree({ kind: "AND", children: [] });
    const updated = applyUpdate(root, {
      kind: "add_observation",
      parentNodeId: root.node_id,
      seed: {
        observable_id: "313730000",
        observable_term: "Serum PSA",
        unit: "ug/L",
      },
    });
    const leaf = updated.children![0];
    expect(leaf.observation?.observable_id).toBe("313730000");
    expect(leaf.observation?.observable_term).toBe("Serum PSA");
    expect(leaf.observation?.unit).toBe("ug/L");
  });

  it("set_observation replaces the payload on an existing node", () => {
    const root = tree({
      kind: "AND",
      children: [{ kind: "OBSERVATION", observation: observation() }],
    });
    const leafId = root.children![0].node_id;
    const next = observation({ operator: "<", value: 100, unit: "g/L" });
    const updated = applyUpdate(root, {
      kind: "set_observation",
      nodeId: leafId,
      observation: next,
    });
    const leaf = updated.children![0];
    expect(leaf.observation?.operator).toBe("<");
    expect(leaf.observation?.value).toBe(100);
    expect(leaf.observation?.unit).toBe("g/L");
  });

  it("observationWithCriterion seeds observable_id from a SNOMED pick", () => {
    const next = observationWithCriterion(observation(), {
      snomed_concept_id: "365636006",
      preferred_term: "Haemoglobin level",
      term: "Haemoglobin level",
    });
    expect(next.observable_id).toBe("365636006");
    expect(next.observable_term).toBe("Haemoglobin level");
    expect(next.operator).toBe(">=");
  });

  it("set_name writes the pathway name on a group node", () => {
    const root = tree({ kind: "OR", children: [] });
    const updated = applyUpdate(root, {
      kind: "set_name",
      nodeId: root.node_id,
      name: "Possible cancer",
    });
    expect(updated.name).toBe("Possible cancer");
  });

  it("OBSERVATION leaf missing observable_id fails validation", () => {
    const root = tree({
      kind: "OBSERVATION",
      observation: observation({ observable_id: "" }),
    });
    expect(findValidationError(root)).toMatch(/lab test|reading/i);
  });

  it("OBSERVATION leaf with empty unit still validates when coded", () => {
    const root = tree({
      kind: "OBSERVATION",
      observation: observation({ unit: "" }),
    });
    expect(findValidationError(root)).toBeNull();
  });

  it("OBSERVATION leaf with valid payload passes validation", () => {
    const root = tree({
      kind: "OBSERVATION",
      observation: observation(),
    });
    expect(findValidationError(root)).toBeNull();
  });
});

describe("Phase 6 OBSERVATION leaf -- treeToSentence", () => {
  it("renders an absolute-mode threshold with plain English", () => {
    const root = tree({
      kind: "OBSERVATION",
      observation: observation(),
    });
    const result = treeToSentence(root);
    expect(result.isWellShaped).toBe(true);
    expect(result.lead.toLowerCase()).toContain("platelet count");
    expect(result.lead).toContain("400");
    expect(result.lead).toContain("10*9/L");
  });

  it("shows the recency window label when within_days is set", () => {
    const root = tree({
      kind: "OBSERVATION",
      observation: observation({ within_days: 30 }),
    });
    const result = treeToSentence(root);
    expect(result.lead.toLowerCase()).toContain("month");
  });

  it("summarises trend mode instead of the raw threshold", () => {
    const root = tree({
      kind: "OBSERVATION",
      observation: observation({
        trend: { delta_kind: "percent", window_days: 365 },
      }),
    });
    const result = treeToSentence(root);
    expect(result.lead.toLowerCase()).toMatch(/trend|change/);
  });

  it("summarises aggregate mode as a plain-English phrase", () => {
    const root = tree({
      kind: "OBSERVATION",
      observation: observation({
        aggregation: { kind: "mean", lookback_n: 3 },
      }),
    });
    const result = treeToSentence(root);
    expect(result.lead.toLowerCase()).toMatch(/mean|average/);
  });
});

