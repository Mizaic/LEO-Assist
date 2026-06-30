/**
 * Jest tests for RULE_FIRED feature -- treeOps unit tests and
 * RuleFiredRow static-source invariant checks.
 *
 * Atlas trace: VT-945821A7 / DI-6AE25829 / DO-274E5A61
 *
 * Test strategy:
 *   - treeOps helpers are pure TS -- exercise them directly.
 *   - RuleFiredRow uses a Popover + fetch -- tested via static-source
 *     assertions so no JSDOM / MUI setup is required.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const RULE_FIRED_ROW = path.join(
  ROOT,
  "services/ui/src/app/admin/guidance/EditRuleDialog/LogicTreeEditor/RuleFiredRow.tsx",
);
const TREE_OPS = path.join(
  ROOT,
  "services/ui/src/app/admin/guidance/EditRuleDialog/treeOps.ts",
);
const TYPES_TS = path.join(
  ROOT,
  "services/ui/src/app/admin/guidance/EditRuleDialog/types.ts",
);

// ---------------------------------------------------------------------------
// Static-source invariants
// ---------------------------------------------------------------------------

describe("RuleFiredRow.tsx -- static-source invariants", () => {
  const src = fs.readFileSync(RULE_FIRED_ROW, "utf-8");

  test("file exists on disk", () => {
    expect(fs.existsSync(RULE_FIRED_ROW)).toBe(true);
  });

  test("exports a default function component", () => {
    expect(src).toContain("export default function RuleFiredRow");
  });

  test("renders outcome toggle with fired / not_fired states", () => {
    expect(src).toContain("has fired");
    expect(src).toContain("has NOT fired");
  });

  test("fires set_rule_fired update when a rule is picked", () => {
    expect(src).toContain('"set_rule_fired"');
  });

  test("fires remove update from delete button", () => {
    expect(src).toContain('"remove"');
  });

  test("contains self-reference exclusion logic (stem comparison)", () => {
    expect(src).toContain("currentStem");
  });

  test("carries Atlas trace for DI-6AE25829", () => {
    expect(src).toContain("DI-6AE25829");
  });
});

describe("types.ts -- RULE_FIRED additions", () => {
  const src = fs.readFileSync(TYPES_TS, "utf-8");

  test("RULE_FIRED is in the LogicNodeKind union", () => {
    expect(src).toContain('"RULE_FIRED"');
  });

  test("EditableLogicNode has referenced_rule_id field", () => {
    expect(src).toContain("referenced_rule_id");
  });

  test("NodeUpdate includes add_rule_fired variant", () => {
    expect(src).toContain('"add_rule_fired"');
  });

  test("NodeUpdate includes set_rule_fired variant", () => {
    expect(src).toContain('"set_rule_fired"');
  });
});

// ---------------------------------------------------------------------------
// treeOps pure-function unit tests
// ---------------------------------------------------------------------------

import {
  applyUpdate,
  assignNodeIds,
  findValidationError,
  isTreeVisuallyEmpty,
  makeRuleFiredNode,
  stripNodeIds,
} from "../app/admin/guidance/EditRuleDialog/treeOps";
import type { EditableLogicNode } from "../app/admin/guidance/EditRuleDialog/types";

function andRoot(children: EditableLogicNode[] = []): EditableLogicNode {
  return assignNodeIds({ kind: "AND", children });
}

describe("makeRuleFiredNode", () => {
  test("returns a node with kind RULE_FIRED", () => {
    const n = makeRuleFiredNode();
    expect(n.kind).toBe("RULE_FIRED");
  });

  test("defaults outcome to fired", () => {
    const n = makeRuleFiredNode();
    expect(n.outcome).toBe("fired");
  });

  test("has a node_id assigned", () => {
    const n = makeRuleFiredNode();
    expect(typeof n.node_id).toBe("string");
    expect(n.node_id.length).toBeGreaterThan(0);
  });
});

describe("applyUpdate -- add_rule_fired", () => {
  test("appends a RULE_FIRED leaf to the parent group", () => {
    const root = andRoot();
    const updated = applyUpdate(root, {
      kind: "add_rule_fired",
      parentNodeId: root.node_id,
    });
    const children = updated?.children ?? [];
    expect(children).toHaveLength(1);
    expect(children[0].kind).toBe("RULE_FIRED");
  });

  test("does not add to a leaf node that cannot have children", () => {
    const root = assignNodeIds({
      kind: "AND",
      children: [{ kind: "CONCEPT", criterion: { snomed_concept_id: "123", preferred_term: "cough" } }],
    });
    const conceptNode = root.children![0];
    const updated = applyUpdate(root, {
      kind: "add_rule_fired",
      parentNodeId: conceptNode.node_id,
    });
    // Root still has one child (the CONCEPT); no new RULE_FIRED added.
    expect(updated?.children).toHaveLength(1);
  });
});

describe("applyUpdate -- set_rule_fired", () => {
  test("updates referenced_rule_id, outcome, and display_name", () => {
    const rfNode = makeRuleFiredNode();
    const root = assignNodeIds({ kind: "AND", children: [rfNode] });
    const updated = applyUpdate(root, {
      kind: "set_rule_fired",
      nodeId: rfNode.node_id,
      referenced_rule_id: "rule:ABC",
      outcome: "not_fired",
      display_name: "Rule ABC",
    });
    const child = updated?.children?.[0];
    expect(child?.referenced_rule_id).toBe("rule:ABC");
    expect(child?.outcome).toBe("not_fired");
    expect(child?.display_name).toBe("Rule ABC");
  });

  test("does not mutate the input tree", () => {
    const rfNode = makeRuleFiredNode();
    const root = assignNodeIds({ kind: "AND", children: [rfNode] });
    applyUpdate(root, {
      kind: "set_rule_fired",
      nodeId: rfNode.node_id,
      referenced_rule_id: "rule:NEW",
      outcome: "fired",
      display_name: "New rule",
    });
    expect(rfNode.referenced_rule_id).toBe("");
  });
});

describe("stripNodeIds -- RULE_FIRED", () => {
  test("includes referenced_rule_id in serialised output", () => {
    const n: EditableLogicNode = {
      node_id: "n1",
      kind: "RULE_FIRED",
      referenced_rule_id: "rule:X",
      outcome: "fired",
      display_name: "Rule X",
    };
    const stripped = stripNodeIds(n);
    expect(stripped.referenced_rule_id).toBe("rule:X");
  });

  test("includes outcome in serialised output", () => {
    const n: EditableLogicNode = {
      node_id: "n1",
      kind: "RULE_FIRED",
      referenced_rule_id: "rule:X",
      outcome: "not_fired",
    };
    const stripped = stripNodeIds(n);
    expect(stripped.outcome).toBe("not_fired");
  });

  test("does not include node_id in serialised output", () => {
    const n: EditableLogicNode = {
      node_id: "n1",
      kind: "RULE_FIRED",
      referenced_rule_id: "rule:X",
      outcome: "fired",
    };
    const stripped = stripNodeIds(n);
    expect(Object.keys(stripped)).not.toContain("node_id");
  });
});

describe("isTreeVisuallyEmpty -- RULE_FIRED", () => {
  test("RULE_FIRED root is not considered visually empty", () => {
    const n: EditableLogicNode = makeRuleFiredNode();
    expect(isTreeVisuallyEmpty(n)).toBe(false);
  });
});

describe("findValidationError -- RULE_FIRED", () => {
  test("returns an error when referenced_rule_id is empty", () => {
    const n: EditableLogicNode = makeRuleFiredNode();
    const err = findValidationError(n);
    expect(typeof err).toBe("string");
    expect((err ?? "").length).toBeGreaterThan(0);
  });

  test("returns null when referenced_rule_id is populated", () => {
    const n: EditableLogicNode = {
      ...makeRuleFiredNode(),
      referenced_rule_id: "rule:ABC",
    };
    expect(findValidationError(n)).toBeNull();
  });
});

describe("treeOps.ts -- static-source invariants", () => {
  const src = fs.readFileSync(TREE_OPS, "utf-8");

  test("KIND_MAP includes RULE_FIRED", () => {
    expect(src).toContain("RULE_FIRED");
  });

  test("makeRuleFiredNode is exported", () => {
    expect(src).toContain("export function makeRuleFiredNode");
  });

  test("add_rule_fired case exists in applyUpdate", () => {
    expect(src).toContain('"add_rule_fired"');
  });

  test("set_rule_fired case exists in applyUpdate", () => {
    expect(src).toContain('"set_rule_fired"');
  });

  test("stripNodeIds handles RULE_FIRED fields", () => {
    expect(src).toContain("referenced_rule_id");
  });
});
