/**
 * Workflow canvas -- auto-layout when Neo4j has no stored positions.
 */

import type { Edge, Node } from "@xyflow/react";
import {
  applyWorkflowLayout,
  estimateNodeHeight,
  needsAutoLayout,
} from "../app/admin/workflows/workflowLayout";
import { ensureContextSpineEdges } from "../app/admin/workflows/workflowGraph";

function node(
  id: string,
  x: number,
  y: number,
): Node {
  return { id, position: { x, y }, data: {}, type: "agent" };
}

describe("needsAutoLayout", () => {
  it("is true when two steps share the same point", () => {
    expect(
      needsAutoLayout([
        node("__start__", 200, 40),
        node("review_6711368", 200, 200),
        node("appointment_booking_6711368", 200, 200),
      ]),
    ).toBe(true);
  });

  it("is true when ranks sit closer than the node height", () => {
    expect(
      needsAutoLayout([
        tallNode("a", 200, 200),
        tallNode("b", 200, 340),
      ]),
    ).toBe(true);
  });

  it("is false when steps already have distinct points", () => {
    expect(
      needsAutoLayout([
        node("__start__", 200, 40),
        node("a", 200, 200),
        node("b", 480, 200),
      ]),
    ).toBe(false);
  });
});

function tallNode(id: string, x: number, y: number): Node {
  return {
    id,
    type: "agent",
    position: { x, y },
    data: {
      agentType: "clinical_summary_agent",
      label: "Clinical Assessment",
      kind: "agent",
    },
  };
}

describe("applyWorkflowLayout", () => {
  it("leaves a gap larger than the node height between ranks", () => {
    const nodes = [
      node("__start__", 200, 40),
      tallNode("clinical", 200, 200),
      tallNode("next", 200, 200),
    ];
    const edges: Edge[] = [
      { id: "e1", source: "__start__", target: "clinical" },
      { id: "e2", source: "clinical", target: "next" },
    ];
    const laid = applyWorkflowLayout(nodes, edges);
    const first = laid.find((n) => n.id === "clinical")!;
    const second = laid.find((n) => n.id === "next")!;
    const height = estimateNodeHeight(first);
    expect(second.position.y).toBeGreaterThanOrEqual(
      first.position.y + height + 24,
    );
  });

  it("lays organisation service scheduler and start on one vertical spine", () => {
    const nodes: Node[] = [
      {
        id: "M0L1I",
        type: "organisation",
        position: { x: 50, y: 40 },
        data: { kind: "organisation", label: "Trust site" },
      },
      {
        id: "6711368",
        type: "service",
        position: { x: 200, y: 40 },
        data: { kind: "service", label: "Fast track" },
      },
      {
        id: "__scheduler__",
        type: "scheduler",
        position: { x: 450, y: 40 },
        data: { kind: "scheduler", label: "Scheduler", derived: true },
      },
      node("__start__", 200, 200),
      tallNode("clinical", 200, 200),
    ];
    const edges: Edge[] = [
      { id: "e-org", source: "M0L1I", target: "6711368" },
      { id: "e-svc", source: "6711368", target: "__scheduler__" },
      { id: "e-sch", source: "__scheduler__", target: "__start__" },
      { id: "e-start", source: "__start__", target: "clinical" },
    ];

    const laid = applyWorkflowLayout(nodes, edges);
    const org = laid.find((n) => n.id === "M0L1I")!;
    const service = laid.find((n) => n.id === "6711368")!;
    const scheduler = laid.find((n) => n.id === "__scheduler__")!;
    const start = laid.find((n) => n.id === "__start__")!;
    const clinical = laid.find((n) => n.id === "clinical")!;

    expect(org.position.y).toBeLessThan(service.position.y);
    expect(service.position.y).toBeLessThan(scheduler.position.y);
    expect(scheduler.position.y).toBeLessThan(start.position.y);
    expect(start.position.y).toBeLessThan(clinical.position.y);
    expect(org.position.x).toBe(service.position.x);
    expect(service.position.x).toBe(scheduler.position.x);
    expect(scheduler.position.x).toBe(start.position.x);

    const schedulerToStart = edges.find(
      (edge) => edge.source === "__scheduler__" && edge.target === "__start__",
    );
    expect(schedulerToStart).toBeDefined();
  });

  it("places organisation and service above start without overlapping", () => {
    const nodes: Node[] = [
      {
        id: "M0L1I",
        type: "organisation",
        position: { x: 200, y: 200 },
        data: {
          kind: "organisation",
          label: "Trust site",
          attributes: [
            { name: "id", value: "M0L1I" },
            { name: "name", value: "Trust site" },
          ],
        },
      },
      {
        id: "6711368",
        type: "service",
        position: { x: 200, y: 200 },
        data: {
          kind: "service",
          label: "Fast track",
          attributes: [
            { name: "id", value: "6711368" },
            { name: "interval", value: "720" },
          ],
        },
      },
      {
        id: "__scheduler__",
        type: "scheduler",
        position: { x: 200, y: 200 },
        data: {
          kind: "scheduler",
          label: "Scheduler",
          derived: true,
          attributes: [
            { name: "source", value: "derived" },
            { name: "serviceInterval", value: "720" },
          ],
        },
      },
      node("__start__", 200, 200),
      tallNode("clinical", 200, 200),
    ];
    const edges: Edge[] = [
      { id: "e-org", source: "M0L1I", target: "6711368" },
      { id: "e-svc", source: "6711368", target: "__start__" },
      { id: "e-sch", source: "__scheduler__", target: "6711368" },
      { id: "e-start", source: "__start__", target: "clinical" },
    ];

    const laid = applyWorkflowLayout(nodes, edges);
    const org = laid.find((n) => n.id === "M0L1I")!;
    const service = laid.find((n) => n.id === "6711368")!;
    const scheduler = laid.find((n) => n.id === "__scheduler__")!;
    const start = laid.find((n) => n.id === "__start__")!;
    const clinical = laid.find((n) => n.id === "clinical")!;

    expect(org.position.y).toBeLessThan(start.position.y);
    expect(service.position.y).toBeLessThan(start.position.y);
    expect(scheduler.position.y).toBeLessThan(start.position.y);
    expect(start.position.y).toBeLessThan(clinical.position.y);

    const boxed = [org, service, scheduler, start, clinical];
    for (let i = 0; i < boxed.length; i += 1) {
      for (let j = i + 1; j < boxed.length; j += 1) {
        const a = boxed[i]!;
        const b = boxed[j]!;
        const aRight = a.position.x + 260;
        const aBottom = a.position.y + estimateNodeHeight(a);
        const bRight = b.position.x + 260;
        const bBottom = b.position.y + estimateNodeHeight(b);
        const overlap =
          a.position.x < bRight &&
          aRight > b.position.x &&
          a.position.y < bBottom &&
          aBottom > b.position.y;
        expect(overlap).toBe(false);
      }
    }
  });

  it("rewrites stale context edges onto the organisation-service-scheduler-start spine", () => {
    const nodes: Node[] = [
      {
        id: "M0L1I",
        type: "organisation",
        position: { x: 0, y: 0 },
        data: { kind: "organisation" },
      },
      {
        id: "6711368",
        type: "service",
        position: { x: 0, y: 0 },
        data: { kind: "service" },
      },
      {
        id: "__scheduler__",
        type: "scheduler",
        position: { x: 0, y: 0 },
        data: { kind: "scheduler" },
      },
      node("__start__", 200, 200),
      tallNode("clinical", 200, 200),
    ];
    const edges: Edge[] = [
      { id: "e-org", source: "M0L1I", target: "6711368" },
      { id: "e-svc", source: "6711368", target: "__start__" },
      { id: "e-sch", source: "__scheduler__", target: "6711368" },
      { id: "e-start", source: "__start__", target: "clinical" },
    ];

    const pairs = ensureContextSpineEdges(nodes, edges).map(
      (edge) => `${edge.source}->${edge.target}`,
    );
    expect(pairs).toEqual([
      "M0L1I->6711368",
      "6711368->__scheduler__",
      "__scheduler__->__start__",
      "__start__->clinical",
    ]);
  });

  it("spreads stacked steps onto different ranks", () => {
    const nodes = [
      node("__start__", 200, 40),
      node("review_6711368", 200, 200),
      node("appointment_booking_6711368", 200, 200),
    ];
    const edges: Edge[] = [
      { id: "e1", source: "__start__", target: "review_6711368" },
      { id: "e2", source: "review_6711368", target: "appointment_booking_6711368" },
    ];

    const laid = applyWorkflowLayout(nodes, edges);
    const review = laid.find((n) => n.id === "review_6711368")!;
    const book = laid.find((n) => n.id === "appointment_booking_6711368")!;
    const start = laid.find((n) => n.id === "__start__")!;

    expect(start.position.y).toBeLessThan(review.position.y);
    expect(review.position.y).toBeLessThan(book.position.y);
    expect(
      `${review.position.x},${review.position.y}`,
    ).not.toBe(`${book.position.x},${book.position.y}`);
  });
});
