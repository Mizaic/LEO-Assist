/**
 * Workflow canvas -- context nodes are display-only on save.
 */

import * as fs from "fs";
import * as path from "path";
import type { Edge, Node } from "@xyflow/react";
import { attributeRowKey } from "../app/admin/workflows/contextAttributes";
import { flowToSaveGraph } from "../app/admin/workflows/workflowGraph";
import type { WorkflowNodeData } from "../app/admin/workflows/types";

function contextNode(
  id: string,
  kind: "service" | "organisation" | "scheduler",
): Node<WorkflowNodeData> {
  return {
    id,
    type: kind,
    position: { x: 0, y: 0 },
    data: {
      agentType: kind,
      label: kind,
      kind,
      readOnly: true,
    },
  };
}

describe("flowToSaveGraph", () => {
  it("omits service organisation and scheduler nodes and their edges", () => {
    const nodes: Node<WorkflowNodeData>[] = [
      contextNode("M0L1I", "organisation"),
      contextNode("6711368", "service"),
      contextNode("__scheduler__", "scheduler"),
      {
        id: "__start__",
        type: "start",
        position: { x: 200, y: 40 },
        data: { agentType: "__start__", label: "Start", kind: "agent" },
      },
      {
        id: "review_6711368",
        type: "human",
        position: { x: 200, y: 200 },
        data: {
          agentType: "clinical_triage",
          label: "Clinical triage",
          kind: "human",
        },
      },
    ];
    const edges: Edge[] = [
      { id: "e-org", source: "M0L1I", target: "6711368" },
      { id: "e-svc", source: "6711368", target: "__start__" },
      { id: "e-sch", source: "__scheduler__", target: "6711368" },
      { id: "e-start", source: "__start__", target: "review_6711368" },
    ];

    const graph = flowToSaveGraph(nodes, edges);

    expect(graph.nodes.map((n) => n.id)).toEqual([
      "__start__",
      "review_6711368",
    ]);
    expect(graph.edges.map((e) => e.id)).toEqual(["e-start"]);
  });
});

describe("start node handles", () => {
  it("accepts an incoming edge from the scheduler on the context spine", () => {
    const src = fs.readFileSync(
      path.resolve(
        __dirname,
        "../app/admin/workflows/[id]/nodes/StartNode.tsx",
      ),
      "utf8",
    );
    expect(src).toMatch(/type="target"/);
    expect(src).toMatch(/type="source"/);
  });
});

describe("context card chrome", () => {
  it("uses theme tokens instead of raw HEX", () => {
    const src = fs.readFileSync(
      path.resolve(
        __dirname,
        "../app/admin/workflows/[id]/nodes/ContextEntityCard.tsx",
      ),
      "utf8",
    );
    expect(src).toMatch(/primary\.dark|info\.main|warning\.main/);
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });
});

describe("context attribute keys", () => {
  const shared = "LEO - DB UAT - Worklist Processing";

  it("gives unique keys when two ambient rows share a label and interval", () => {
    const rows = [
      { name: "ambient", value: shared, id: "worklist_aaa" },
      { name: "interval", value: `${shared}: 720 min`, id: "worklist_aaa" },
      { name: "ambient", value: shared, id: "worklist_bbb" },
      { name: "interval", value: `${shared}: 720 min`, id: "worklist_bbb" },
    ];
    const keys = rows.map((row, index) => attributeRowKey(row, index));
    expect(new Set(keys).size).toBe(4);
    expect(keys.some((key) => key === `ambient-${shared}`)).toBe(false);
  });

  it("does not key attribute rows by label alone", () => {
    const card = fs.readFileSync(
      path.resolve(
        __dirname,
        "../app/admin/workflows/[id]/nodes/ContextEntityCard.tsx",
      ),
      "utf8",
    );
    const panel = fs.readFileSync(
      path.resolve(
        __dirname,
        "../app/admin/workflows/[id]/PropertiesPanel.tsx",
      ),
      "utf8",
    );
    expect(card).not.toMatch(/key=\{`\$\{row\.name\}-\$\{row\.value\}`\}/);
    expect(panel).not.toMatch(/key=\{`\$\{row\.name\}-\$\{row\.value\}`\}/);
    expect(card).toMatch(/attributeRowKey/);
    expect(panel).toMatch(/attributeRowKey/);
  });
});
