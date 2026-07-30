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
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import HighlightWizard, { type WizardJumpRequest } from "../HighlightWizard";
import { WIZARD_TOOLTIPS } from "../HighlightWizard/copy";
import { applyUpdate } from "../treeOps";
import type { EditableLogicNode, NodeUpdate } from "../types";

// Buttons wrapped directly in a MUI Tooltip get their accessible name
// from the tooltip's `title`, not their visible label (MUI v7 default:
// `describeChild=false` -- see WIZARD_TOOLTIPS's "Keep aria-labels" doc
// comment in copy.ts). "Confirm situation X" and "Confirm merge" are
// the exceptions: their Tooltip wraps an extra <span> (needed because a
// conditionally-disabled Button drops pointer events), and aria-label
// on that span does not propagate to the nested <button>, so those two
// keep their own visible text as the accessible name.

// jsdom does not implement scrollIntoView -- see useJumpScrollAndFlash's
// doc comment for why the "jump to issue" flow calls it.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = jest.fn();
}

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
  recommendationText = TEXT,
  onSelectNode = jest.fn(),
  onEditConcept = jest.fn(),
}: {
  initialTree: EditableLogicNode;
  recommendationText?: string;
  onSelectNode?: (nodeId: string, anchor?: HTMLElement | null) => void;
  onEditConcept?: (nodeId: string) => void;
}) {
  const [tree, setTree] = useState(initialTree);
  function handleUpdate(update: NodeUpdate) {
    setTree((curr) => applyUpdate(curr, update) ?? curr);
  }
  return (
    <HighlightWizard
      tree={tree}
      recommendationText={recommendationText}
      selectedNodeId={null}
      onSelectNode={onSelectNode}
      onUpdate={handleUpdate}
      onRequestAdd={jest.fn()}
      onEditConcept={onEditConcept}
      startMode="fresh"
    />
  );
}

describe("HighlightWizard: Step 1 (prerequisites)", () => {
  it("shows the Step 1 header and auto-anchors the existing age check", () => {
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    render(<Harness initialTree={tree} />);
    expect(screen.getByText(/what must always be true/i)).toBeInTheDocument();
    expect(screen.getByTestId(`prerequisite-row-${"age"}`)).toHaveAttribute(
      "data-has-anchor",
      "true",
    );
  });

  it("advances to Step 2 when the reviewer says nothing else always applies", async () => {
    const user = userEvent.setup();
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    render(<Harness initialTree={tree} />);
    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.noMore, "i") }));
    expect(
      screen.getByText(/does this apply the same way to everyone/i),
    ).toBeInTheDocument();
  });

  it("reports its own step via onStepChange, once on mount and again on every advance", async () => {
    const user = userEvent.setup();
    const onStepChange = jest.fn();
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    render(
      <HighlightWizard
        tree={tree}
        recommendationText={TEXT}
        selectedNodeId={null}
        onSelectNode={jest.fn()}
        onUpdate={jest.fn()}
        onRequestAdd={jest.fn()}
        onEditConcept={jest.fn()}
        onStepChange={onStepChange}
        startMode="fresh"
      />,
    );
    expect(onStepChange).toHaveBeenCalledWith("prerequisites");
    onStepChange.mockClear();

    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.noMore, "i") }));
    expect(onStepChange).toHaveBeenCalledWith("pathway-split");
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
  await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.noMore, "i") }));
  return user;
}

describe("HighlightWizard: Step 2 -> Step 3 with an already-drafted tree", () => {
  it("jumps straight to Step 3 with no tree mutation when the pathways already exist", async () => {
    render(<Harness initialTree={preDraftedTree()} />);
    const user = await advanceToStep2();
    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));

    expect(screen.getByText(/situation a \(1 of 2\)/i)).toBeInTheDocument();
    // Pathway A's own row spans the whole first clause ("In people
    // aged 55 or over with weight loss") since there is no nested
    // list under it -- it resolves because the existing "weight loss"
    // CONCEPT leaf's own match range falls inside that span.
    expect(screen.getByTestId("list-row-0-42")).toHaveAttribute("data-resolved", "true");
  });

  it("routes clicking an already-resolved Step 3 row to onEditConcept, not onSelectNode", async () => {
    const onSelectNode = jest.fn();
    const onEditConcept = jest.fn();
    render(
      <Harness
        initialTree={preDraftedTree()}
        onSelectNode={onSelectNode}
        onEditConcept={onEditConcept}
      />,
    );
    const user = await advanceToStep2();
    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));

    await user.click(screen.getByTestId("list-row-0-42"));

    expect(onEditConcept).toHaveBeenCalledWith("wl");
    expect(onSelectNode).not.toHaveBeenCalled();
  });

  it("walks both pathways and lands on Review once the last one confirms", async () => {
    render(<Harness initialTree={preDraftedTree()} />);
    const user = await advanceToStep2();
    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));

    await user.click(screen.getByRole("button", { name: /confirm situation a/i }));
    expect(screen.getByText(/situation b \(2 of 2\)/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm situation b/i }));
    expect(screen.getByTestId("wizard-review")).toBeInTheDocument();
    expect(screen.getByText(/check the live preview/i)).toBeInTheDocument();
    expect(screen.queryByTestId("sentence-editor")).not.toBeInTheDocument();
  });


  it("Back from Step 3's first pathway returns to Step 2", async () => {
    render(<Harness initialTree={preDraftedTree()} />);
    const user = await advanceToStep2();
    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));
    await user.click(screen.getByTestId("wizard-back"));
    expect(
      screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.merge, "i") }),
    ).toBeInTheDocument();
  });

  it("reports 'review' via onStepChange only once every pathway is confirmed", async () => {
    const onStepChange = jest.fn();
    render(
      <HighlightWizard
        tree={preDraftedTree()}
        recommendationText={TEXT}
        selectedNodeId={null}
        onSelectNode={jest.fn()}
        onUpdate={jest.fn()}
        onRequestAdd={jest.fn()}
        onEditConcept={jest.fn()}
        onStepChange={onStepChange}
        startMode="fresh"
      />,
    );
    const user = await advanceToStep2();
    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));
    expect(onStepChange).not.toHaveBeenCalledWith("review");

    await user.click(screen.getByRole("button", { name: /confirm situation a/i }));
    expect(onStepChange).not.toHaveBeenCalledWith("review");

    await user.click(screen.getByRole("button", { name: /confirm situation b/i }));
    expect(onStepChange).toHaveBeenCalledWith("review");
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
    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));

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
        onEditConcept={jest.fn()}
        startMode="fresh"
      />
    );
  }

  it("treats the whole tree as one situation with no tree mutation needed", async () => {
    const user = userEvent.setup();
    render(<SingleSituationHarness />);
    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.noMore, "i") }));

    const noSplitBtn = await screen.findByRole("button", {
      name: RegExp(WIZARD_TOOLTIPS.noSplit, "i"),
    });
    await user.click(noSplitBtn);

    expect(screen.getByText(/situation a \(1 of 1\)/i)).toBeInTheDocument();
    // The sole text row for this sentence is currently auto-resolved by
    // the age DEMOGRAPHIC ("is 55 years or older"), so the Weight loss
    // CONCEPT would not appear as a matched row. Step 3 must still
    // surface it via the confirmed-conditions fallback (same class as
    // the tree-rehydration orphan fix) rather than letting it vanish.
    expect(
      within(screen.getByTestId("pathway-confirmed-condition-wl")).getByText(/weight loss/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm situation a/i }));
    expect(screen.getByTestId("wizard-review")).toBeInTheDocument();
    expect(screen.getByText(/check the live preview/i)).toBeInTheDocument();
  });
});

/** Drives a `WizardJumpRequest` at the wizard from outside, the same
 *  way EditRuleDialog's issue banner does -- a "Jump" button issues a
 *  fresh request (new requestId) targeting whichever nodeId the test
 *  wants to land on. */
function JumpHarness({
  initialTree,
  initialStep,
}: {
  initialTree: EditableLogicNode;
  initialStep?: "fresh" | "auto";
}) {
  const [tree, setTree] = useState(initialTree);
  const [jumpRequest, setJumpRequest] = useState<WizardJumpRequest | null>(null);
  return (
    <div>
      <button onClick={() => setJumpRequest({ nodeId: "age", requestId: Date.now() })}>
        Jump to age
      </button>
      <button onClick={() => setJumpRequest({ nodeId: "vo", requestId: Date.now() })}>
        Jump to vomiting
      </button>
      <HighlightWizard
        tree={tree}
        recommendationText={TEXT}
        selectedNodeId={null}
        onSelectNode={jest.fn()}
        onUpdate={(u) => setTree((curr) => applyUpdate(curr, u) ?? curr)}
        onRequestAdd={jest.fn()}
        onEditConcept={jest.fn()}
        startMode={initialStep ?? "fresh"}
        jumpRequest={jumpRequest}
      />
    </div>
  );
}

describe("HighlightWizard: jump-to-issue navigation (WizardJumpRequest)", () => {
  it("jumps from Review back to Step 1 when the target node lives in prerequisites", async () => {
    const user = userEvent.setup();
    render(<JumpHarness initialTree={preDraftedTree()} />);
    const advanceUser = await advanceToStep2();
    await advanceUser.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));
    await advanceUser.click(screen.getByRole("button", { name: /confirm situation a/i }));
    await advanceUser.click(screen.getByRole("button", { name: /confirm situation b/i }));
    expect(screen.getByTestId("wizard-review")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /jump to age/i }));

    expect(screen.getByText(/what must always be true/i)).toBeInTheDocument();
    expect(screen.getByTestId("prerequisite-row-age")).toHaveAttribute(
      "data-node-id",
      "age",
    );
  });

  it("jumps straight to the pathway that owns the target node, skipping earlier pathways", async () => {
    // "auto" (the real default -- see HighlightWizardProps) recognises
    // this pre-drafted tree as already built and starts at Review with
    // boundaries already resolved, exactly like reopening a saved rule.
    const user = userEvent.setup();
    render(<JumpHarness initialTree={preDraftedTree()} initialStep="auto" />);
    expect(await screen.findByTestId("wizard-review")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /jump to vomiting/i }));

    expect(await screen.findByText(/situation b \(2 of 2\)/i)).toBeInTheDocument();
  });

  it("calls scrollIntoView on the row matching the jumped-to node", async () => {
    const user = userEvent.setup();
    const scrollSpy = jest.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    render(<JumpHarness initialTree={preDraftedTree()} initialStep="auto" />);
    expect(await screen.findByTestId("wizard-review")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /jump to age/i }));

    await screen.findByTestId("prerequisite-row-age");
    await waitFor(() => expect(scrollSpy).toHaveBeenCalled());
  });

  it("does nothing when the requested node is not in the tree at all", async () => {
    const user = userEvent.setup();
    function StaleJumpHarness() {
      const [jumpRequest, setJumpRequest] = useState<WizardJumpRequest | null>(null);
      return (
        <div>
          <button onClick={() => setJumpRequest({ nodeId: "no-such-node", requestId: Date.now() })}>
            Jump nowhere
          </button>
          <HighlightWizard
            tree={preDraftedTree()}
            recommendationText={TEXT}
            selectedNodeId={null}
            onSelectNode={jest.fn()}
            onUpdate={jest.fn()}
            onRequestAdd={jest.fn()}
            onEditConcept={jest.fn()}
            startMode="fresh"
            jumpRequest={jumpRequest}
          />
        </div>
      );
    }
    render(<StaleJumpHarness />);
    await user.click(screen.getByRole("button", { name: /jump nowhere/i }));

    // Still on Step 1 -- nothing to jump to, so no-op rather than a crash.
    expect(screen.getByText(/what must always be true/i)).toBeInTheDocument();
  });
});

/** Three " or "-joined clauses so a merge in Step 2 is a genuine edit
 *  (3 -> 2), not a no-op -- lets these tests tell "Back re-derived
 *  fresh boundaries from scratch" (would show 3 rows again) apart
 *  from "Back correctly kept the reviewer's own merge" (still 2). */
const THREE_SITUATION_TEXT =
  "In people aged 55 or over with: upper abdominal pain, or " +
  "indigestion with any of the following: nausea, vomiting or " +
  "weight loss, or nausea with any of the following: weight loss, " +
  "heartburn or indigestion.";

describe("HighlightWizard: Back to Step 2 keeps the reviewer's own merge/split edits", () => {
  it("does not re-derive fresh boundaries -- Back shows the merged-down count, not the original heuristic count", async () => {
    const user = userEvent.setup();
    const tree: EditableLogicNode = { node_id: "root", kind: "AND", children: [ageLeaf()] };
    render(<Harness initialTree={tree} recommendationText={THREE_SITUATION_TEXT} />);

    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.noMore, "i") }));
    expect(screen.getAllByTestId(/^pathway-boundary-row-/)).toHaveLength(3);

    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.merge, "i") }));
    const rows = screen.getAllByTestId(/^pathway-boundary-row-/);
    await user.click(rows[0]);
    await user.click(rows[1]);
    await user.click(screen.getByRole("button", { name: /confirm merge/i }));
    expect(screen.getAllByTestId(/^pathway-boundary-row-/)).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));
    expect(await screen.findByText(/situation a \(1 of 2\)/i)).toBeInTheDocument();

    await user.click(screen.getByTestId("wizard-back"));

    expect(
      screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.merge, "i") }),
    ).toBeInTheDocument();
    // The old bug: this would show 3 rows again (freshly re-derived
    // from THREE_SITUATION_TEXT), silently discarding the merge.
    expect(screen.getAllByTestId(/^pathway-boundary-row-/)).toHaveLength(2);
  });
});

describe("HighlightWizard: warns before a Step 2 count change would wipe Step 3 leaves", () => {
  it("shows a confirm dialog, and Cancel leaves the tree and boundaries untouched", async () => {
    render(<Harness initialTree={preDraftedTree()} />);
    const advanceUser = await advanceToStep2();
    await advanceUser.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));
    await advanceUser.click(screen.getByTestId("wizard-back"));

    // Split situation A's row into two -- boundaries.length goes from
    // 2 to 3, but the tree still only has 2 pathways, one of which
    // (pw-a) already has a resolved "weight loss" leaf.
    await advanceUser.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.split, "i") }));
    const rowsToSplit = screen.getAllByTestId(/^pathway-boundary-row-/);
    await advanceUser.click(rowsToSplit[0]);
    const firstWord = screen.getByText(/^In$/);
    await advanceUser.click(firstWord);
    await advanceUser.click(screen.getByRole("button", { name: /confirm selection/i }));

    await advanceUser.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/this will remove what you've already added/i),
    ).toBeInTheDocument();
    // Still on Step 2 with the split applied -- the warning blocked
    // the tree mutation, not the boundary edit itself. (The dialog's
    // focus trap marks the rest of the page aria-hidden, so check via
    // test id rather than an accessible-role query here.)
    expect(screen.getAllByTestId(/^pathway-boundary-row-/)).toHaveLength(3);

    await advanceUser.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.merge, "i") }),
    ).toBeInTheDocument();
  });

  it("Confirm on the warning proceeds and rebuilds Step 3 with fresh, empty pathways", async () => {
    render(<Harness initialTree={preDraftedTree()} />);
    const advanceUser = await advanceToStep2();
    await advanceUser.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));
    await advanceUser.click(screen.getByTestId("wizard-back"));

    await advanceUser.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.split, "i") }));
    const rowsToSplit = screen.getAllByTestId(/^pathway-boundary-row-/);
    await advanceUser.click(rowsToSplit[0]);
    const firstWord = screen.getByText(/^In$/);
    await advanceUser.click(firstWord);
    await advanceUser.click(screen.getByRole("button", { name: /confirm selection/i }));
    await advanceUser.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));

    const dialog = await screen.findByRole("dialog");
    await advanceUser.click(
      within(dialog).getByRole("button", { name: /yes, replace them/i }),
    );

    expect(await screen.findByText(/situation a \(1 of 3\)/i)).toBeInTheDocument();
    // Freshly rebuilt -- the previously-resolved "weight loss" leaf
    // under the old situation A is gone; every row in the new
    // 3-situation split starts unresolved.
    const rows = screen.getAllByTestId(/^list-row-/);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((row) => row.getAttribute("data-resolved") === "false")).toBe(true);
  });

  it("does not warn when re-confirming the SAME count, even with resolved leaves already in place", async () => {
    render(<Harness initialTree={preDraftedTree()} />);
    const advanceUser = await advanceToStep2();
    await advanceUser.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));
    await advanceUser.click(screen.getByTestId("wizard-back"));

    await advanceUser.click(screen.getByRole("button", { name: RegExp(WIZARD_TOOLTIPS.looksRight, "i") }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByText(/situation a \(1 of 2\)/i)).toBeInTheDocument();
    expect(screen.getByTestId("list-row-0-42")).toHaveAttribute("data-resolved", "true");
  });
});
