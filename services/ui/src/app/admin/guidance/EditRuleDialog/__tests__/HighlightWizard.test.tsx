/**
 * Live-render tests for the highlight-to-build wizard orchestrator --
 * the full Step 1 -> Step 2 -> Step 3 (repeated) -> Review flow,
 * driven against the real `applyUpdate` tree reducer so materialization
 * (reuse an existing pathway split vs. build a fresh one) and row
 * resolution are exercised exactly as they run in production, not
 * against a mocked tree.
 *
 * Per the highlight-to-build wizard plan's `wizard-orchestrator` todo.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React, { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import HighlightWizard from "../HighlightWizard";
import { applyUpdate } from "../treeOps";
import type { EditableLogicNode, NodeUpdate } from "../types";

const TEXT = "In people aged 55 or over with weight loss, or nausea and vomiting.";

function ageLeaf(): EditableLogicNode {
  return { node_id: "age", kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: "55" };
}

function conceptLeaf(id: string, term: string): EditableLogicNode {
  return { node_id: id, kind: "CONCEPT", criterion: { snomed_concept_id: id, preferred_term: term } };
}

/** Mirrors how EditRuleDialog/index.tsx really drives the wizard:
 *  owns the tree via useState and threads onUpdate through the real
 *  `applyUpdate` reducer, so a mutation the wizard emits actually
 *  changes what the wizard sees on its next render. */
function Harness({
  initialTree,
  onSkipToManual = jest.fn(),
  onSelectNode = jest.fn(),
}: {
  initialTree: EditableLogicNode;
  onSkipToManual?: () => void;
  onSelectNode?: (nodeId: string, anchor?: HTMLElement | null) => void;
}) {
  const [tree, setTree] = useState(initialTree);
  function handleUpdate(update: NodeUpdate) {
    setTree((curr) => applyUpdate(curr, update) ?? curr);
  }
  return (
    <HighlightWizard
      tree={tree}
      recommendationText={TEXT}
      selectedNodeId={null}
      onSelectNode={onSelectNode}
      onUpdate={handleUpdate}
      onRequestAdd={jest.fn()}
      onSkipToManual={onSkipToManual}
    />
  );
}

describe("HighlightWizard: Step 1 (prerequisites)", () => {
  it("shows the Step 1 header and auto-anchors the existing age check", () => {
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    render(<Harness initialTree={tree} />);
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(screen.getByTestId(`prerequisite-row-${"age"}`)).toHaveAttribute(
      "data-has-anchor",
      "true",
    );
  });

  it("advances to Step 2 when the reviewer says nothing else always applies", async () => {
    const user = userEvent.setup();
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    render(<Harness initialTree={tree} />);
    await user.click(screen.getByRole("button", { name: /no, nothing else/i }));
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
  });

  it("calls onSkipToManual from the header at any step", async () => {
    const user = userEvent.setup();
    const onSkipToManual = jest.fn();
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    render(<Harness initialTree={tree} onSkipToManual={onSkipToManual} />);
    await user.click(screen.getByRole("button", { name: /skip to advanced view/i }));
    expect(onSkipToManual).toHaveBeenCalledTimes(1);
  });
});

/** A tree whose OR already has the same 2 pathways the ", or "
 *  heuristic will find in TEXT -- materialization should be a pure
 *  read (no onUpdate calls needed), so Step 2's confirm jumps
 *  straight to Step 3 with the existing leaves already resolved. */
function preDraftedTree(): EditableLogicNode {
  return {
    node_id: "root",
    kind: "AND",
    children: [
      ageLeaf(),
      {
        node_id: "or",
        kind: "OR",
        children: [
          { node_id: "pw-a", kind: "AND", pathway_key: "pw_a", children: [conceptLeaf("wl", "Weight loss")] },
          {
            node_id: "pw-b",
            kind: "AND",
            pathway_key: "pw_b",
            children: [conceptLeaf("na", "Nausea"), conceptLeaf("vo", "Vomiting")],
          },
        ],
      },
    ],
  };
}

async function advanceToStep2() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /no, nothing else/i }));
  return user;
}

describe("HighlightWizard: Step 2 -> Step 3 with an already-drafted tree", () => {
  it("jumps straight to Step 3 with no tree mutation when the pathways already exist", async () => {
    render(<Harness initialTree={preDraftedTree()} />);
    const user = await advanceToStep2();
    await user.click(screen.getByRole("button", { name: /looks right, continue/i }));

    expect(screen.getByText(/situation a \(1 of 2\)/i)).toBeInTheDocument();
    // Pathway A's own row spans the whole first clause ("In people
    // aged 55 or over with weight loss") since there is no nested
    // list under it -- it resolves because the existing "weight loss"
    // CONCEPT leaf's own match range falls inside that span.
    expect(screen.getByTestId("list-row-0-42")).toHaveAttribute("data-resolved", "true");
  });

  it("walks both pathways and lands on Review once the last one confirms", async () => {
    render(<Harness initialTree={preDraftedTree()} />);
    const user = await advanceToStep2();
    await user.click(screen.getByRole("button", { name: /looks right, continue/i }));

    await user.click(screen.getByRole("button", { name: /confirm situation a/i }));
    expect(screen.getByText(/situation b \(2 of 2\)/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm situation b/i }));
    expect(screen.getByText(/here's the rule you built/i)).toBeInTheDocument();
    expect(screen.getByTestId("sentence-editor")).toBeInTheDocument();
  });

  it("Back from Step 3's first pathway returns to Step 2", async () => {
    render(<Harness initialTree={preDraftedTree()} />);
    const user = await advanceToStep2();
    await user.click(screen.getByRole("button", { name: /looks right, continue/i }));
    await user.click(screen.getByRole("button", { name: /^back$/i }));
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
  });
});

/** A rule with no pathway split at all yet -- Step 2's confirm must
 *  emit a `replace_root` and the wizard must wait (rendering the
 *  "materializing" status) until that mutation lands before Step 3
 *  can read the freshly created pathway nodes. */
describe("HighlightWizard: Step 2 -> Step 3 building fresh pathways from scratch", () => {
  it("waits for materialization, then renders Step 3 with two empty pathways", async () => {
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    render(<Harness initialTree={tree} />);
    const user = await advanceToStep2();
    await user.click(screen.getByRole("button", { name: /looks right, continue/i }));

    expect(await screen.findByText(/situation a \(1 of 2\)/i)).toBeInTheDocument();
    // Freshly created pathways start with nothing resolved yet.
    expect(screen.getByTestId("list-row-0-42")).toHaveAttribute("data-resolved", "false");
  });
});

describe("HighlightWizard: the 'no split' escape hatch", () => {
  /** No top-level " or " connector at all -- one situation for
   *  everyone, so Step 2 should offer "Doesn't split" directly rather
   *  than a multi-row boundary list. */
  const SINGLE_SITUATION_TEXT = "In people aged 55 and over with weight loss.";

  function SingleSituationHarness() {
    const [tree, setTree] = useState<EditableLogicNode>({
      node_id: "root",
      kind: "AND",
      children: [ageLeaf(), conceptLeaf("wl", "Weight loss")],
    });
    return (
      <HighlightWizard
        tree={tree}
        recommendationText={SINGLE_SITUATION_TEXT}
        selectedNodeId={null}
        onSelectNode={jest.fn()}
        onUpdate={(u) => setTree((curr) => applyUpdate(curr, u) ?? curr)}
        onRequestAdd={jest.fn()}
        onSkipToManual={jest.fn()}
      />
    );
  }

  it("treats the whole tree as one situation with no tree mutation needed", async () => {
    const user = userEvent.setup();
    render(<SingleSituationHarness />);
    await user.click(screen.getByRole("button", { name: /no, nothing else/i }));

    const noSplitBtn = await screen.findByRole("button", { name: /doesn't split/i });
    await user.click(noSplitBtn);

    expect(screen.getByText(/situation a \(1 of 1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/weight loss/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm situation a/i }));
    expect(screen.getByText(/here's the rule you built/i)).toBeInTheDocument();
  });
});
