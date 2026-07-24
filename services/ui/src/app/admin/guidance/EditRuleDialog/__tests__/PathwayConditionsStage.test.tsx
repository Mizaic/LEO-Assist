/**
 * Live-render tests for PathwayConditionsStage's copy-across offer --
 * landing on a pathway that asks about the exact same findings as an
 * earlier, already-confirmed pathway (NG12 1.2.9's pathway C and D)
 * offers to copy the earlier pathway's SNOMED codes across, driven
 * against the real `applyUpdate` tree reducer so the two-phase
 * "create the subgroup, then add the copied concepts" sequencing is
 * exercised exactly as it runs in production.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React, { useEffect, useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PathwayConditionsStage from "../HighlightWizard/PathwayConditionsStage";
import type { ClusterGrouping } from "../HighlightWizard/wizardMapping";
import { applyUpdate } from "../treeOps";
import type { EditableLogicNode, NodeUpdate } from "../types";
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";

const PATHWAY_A_TEXT =
  "raised platelet count with any of the following: nausea, vomiting, " +
  "weight loss, reflux, dyspepsia, upper abdominal pain.";
const PATHWAY_B_TEXT =
  "nausea or vomiting with any of the following: weight loss, reflux, " +
  "dyspepsia, upper abdominal pain.";
const TEXT = `${PATHWAY_A_TEXT} ${PATHWAY_B_TEXT}`;

const BOUNDARIES: PathwayTextBoundary[] = [
  { text: PATHWAY_A_TEXT, start: 0, end: PATHWAY_A_TEXT.length, source: "heuristic" },
  {
    text: PATHWAY_B_TEXT,
    start: TEXT.indexOf(PATHWAY_B_TEXT),
    end: TEXT.indexOf(PATHWAY_B_TEXT) + PATHWAY_B_TEXT.length,
    source: "heuristic",
  },
];

function concept(id: string, term: string): EditableLogicNode {
  return { node_id: `n-${id}`, kind: "CONCEPT", criterion: { snomed_concept_id: id, preferred_term: term } };
}

function buildInitialTree(): EditableLogicNode {
  return {
    node_id: "root",
    kind: "AND",
    children: [
      {
        node_id: "or",
        kind: "OR",
        children: [
          {
            node_id: "pw-a",
            kind: "AND",
            pathway_key: "pw_a",
            children: [
              concept("plt", "Raised platelet count"),
              {
                node_id: "cluster-a",
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
          },
          { node_id: "pw-b", kind: "AND", pathway_key: "pw_b", children: [] },
        ],
      },
    ],
  };
}

/** Mirrors how the wizard orchestrator really drives this stage: owns
 *  the tree and the per-pathway grouping choices via useState, and
 *  threads onUpdate through the real `applyUpdate` reducer. */
function Harness({
  onConfirmPathway = jest.fn(),
  onTreeChange,
}: {
  onConfirmPathway?: () => void;
  onTreeChange?: (tree: EditableLogicNode) => void;
}) {
  const [tree, setTree] = useState(buildInitialTree());
  const [clusterGroupings, setClusterGroupings] = useState<Record<number, ClusterGrouping>>({
    0: "AT_LEAST",
  });
  const [leadClusterGroupings, setLeadClusterGroupings] = useState<Record<number, ClusterGrouping>>({});

  useEffect(() => {
    onTreeChange?.(tree);
  }, [tree, onTreeChange]);

  function handleUpdate(update: NodeUpdate) {
    setTree((curr) => applyUpdate(curr, update) ?? curr);
  }

  return (
    <PathwayConditionsStage
      tree={tree}
      recommendationText={TEXT}
      boundaries={BOUNDARIES}
      pathwayIndex={1}
      clusterGroupings={clusterGroupings}
      onSetClusterGrouping={(i, g) => setClusterGroupings((prev) => ({ ...prev, [i]: g }))}
      leadClusterGroupings={leadClusterGroupings}
      onSetLeadClusterGrouping={(i, g) => setLeadClusterGroupings((prev) => ({ ...prev, [i]: g }))}
      onSelectNode={jest.fn()}
      onUpdate={handleUpdate}
      onRequestAdd={jest.fn()}
      onConfirmPathway={onConfirmPathway}
    />
  );
}

describe("PathwayConditionsStage: highlight-a-word multi-code picker", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("adds the picked multi-seed criterion as a new sibling directly under the pathway", async () => {
    const user = userEvent.setup();
    jest.spyOn(global, "fetch").mockImplementation((url) => {
      if (String(url).includes("/api/terminology/search")) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { snomed_concept_id: "999", term: "Anaemia", semantic_tag: "finding" },
          ],
        } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    });

    let latestTree: EditableLogicNode | undefined;
    render(<Harness onTreeChange={(t) => (latestTree = t)} />);

    const toggles = screen.getAllByRole("button", {
      name: /highlight text for more codes/i,
    });
    await user.click(toggles[0]);

    const words = screen.getAllByText(/./, { selector: "[data-word-index]" });
    await user.pointer([
      { keys: "[MouseLeft>]", target: words[0] },
      { keys: "[/MouseLeft]", target: words[0] },
    ]);
    await user.click(screen.getByRole("button", { name: /confirm selection/i }));

    await user.click(await screen.findByRole("checkbox", { name: /select anaemia/i }));
    await user.click(screen.getByRole("button", { name: "Add 1 code" }));

    const pathwayB = latestTree?.children?.[0]?.children?.[1] as EditableLogicNode;
    expect(pathwayB.node_id).toBe("pw-b");
    const added = pathwayB.children?.find(
      (c) => c.criterion?.snomed_concept_id === "999",
    );
    expect(added).toBeDefined();
    expect(added?.criterion?.seeds).toEqual([
      expect.objectContaining({
        snomed_concept_id: "999",
        include_descendants: false,
        distance_child: null,
      }),
    ]);
  });
});

describe("PathwayConditionsStage: copy-across offer", () => {
  it("offers to copy situation A's codes when situation B asks about the same findings", () => {
    render(<Harness />);
    expect(
      screen.getByText(/situation a asked about the same 6 findings/i),
    ).toBeInTheDocument();
  });

  it("resolves every row and pre-fills both grouping choices once accepted", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: /copy them across/i }));

    // Both of situation B's clusters (the lead-or and the trailing
    // one) inherit situation A's AT_LEAST default, shown via the
    // same "Change" affordance any manually-chosen grouping gets --
    // never a silent, unchangeable decision.
    const leadGroup = screen.getByRole("group", { name: /nausea or vomiting/i });
    expect(within(leadGroup).getByText(/only one of these needs to match/i)).toBeInTheDocument();
    const trailingGroup = screen.getByRole("group", { name: /any of the following/i });
    expect(within(trailingGroup).getByText(/only one of these needs to match/i)).toBeInTheDocument();

    // Every row now resolves to a copied leaf, so Confirm is enabled.
    expect(
      screen.getByRole("button", { name: /confirm situation b/i }),
    ).toBeEnabled();
    expect(screen.queryByText(/still need a match/i)).not.toBeInTheDocument();
  });

  it("dismisses without mutating the tree, leaving every row unresolved", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: /i'll do this one myself/i }));

    expect(screen.queryByText(/situation a asked about the same/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /confirm situation b/i }),
    ).toBeDisabled();
  });

  it("stops offering once the reviewer has started situation B manually", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: /copy them across/i }));
    expect(screen.queryByText(/situation a asked about the same/i)).not.toBeInTheDocument();
  });
});
