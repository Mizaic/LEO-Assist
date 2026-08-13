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
  onSelectNode = jest.fn(),
  onEditConcept = jest.fn(),
  pathwayIndex = 1,
}: {
  onConfirmPathway?: () => void;
  onTreeChange?: (tree: EditableLogicNode) => void;
  onSelectNode?: (nodeId: string, anchor?: HTMLElement | null) => void;
  onEditConcept?: (nodeId: string) => void;
  pathwayIndex?: number;
}) {
  const [tree, setTree] = useState(buildInitialTree());
  // "pw_a" -- pathway A's own stable pathway_key (see buildInitialTree)
  // -- not the array index, per pathwayGroupingKey's re-keying.
  const [clusterGroupings, setClusterGroupings] = useState<Record<string, ClusterGrouping>>({
    pw_a: "AT_LEAST",
  });
  const [leadClusterGroupings, setLeadClusterGroupings] = useState<Record<string, ClusterGrouping>>({});
  const [dismissedCopyAcrossOffers, setDismissedCopyAcrossOffers] = useState<Set<string>>(
    () => new Set(),
  );

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
      pathwayIndex={pathwayIndex}
      clusterGroupings={clusterGroupings}
      onSetClusterGrouping={(k, g) => setClusterGroupings((prev) => ({ ...prev, [k]: g }))}
      leadClusterGroupings={leadClusterGroupings}
      onSetLeadClusterGrouping={(k, g) => setLeadClusterGroupings((prev) => ({ ...prev, [k]: g }))}
      dismissedCopyAcrossOffers={dismissedCopyAcrossOffers}
      onDismissCopyAcrossOffer={(k) =>
        setDismissedCopyAcrossOffers((prev) => new Set(prev).add(k))
      }
      onSelectNode={onSelectNode}
      onUpdate={handleUpdate}
      onRequestAdd={jest.fn()}
      onEditConcept={onEditConcept}
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

describe("PathwayConditionsStage: editing an already-resolved row", () => {
  it("routes a click on an already-matched CONCEPT row to onEditConcept, not onSelectNode -- it already has a code, so it needs add/remove, not a single-pick override", async () => {
    const user = userEvent.setup();
    const onSelectNode = jest.fn();
    const onEditConcept = jest.fn();
    render(<Harness pathwayIndex={0} onSelectNode={onSelectNode} onEditConcept={onEditConcept} />);

    // Situation A's own lead-in row ("raised platelet count", ahead of
    // its "any of the following" cluster) already resolves to the
    // "plt" leaf seeded in buildInitialTree. Targeted by testid, not
    // text, since the row's "matched to: Raised platelet count"
    // caption also contains the same words.
    const leadRowTestId = `list-row-0-${"raised platelet count".length}`;
    await user.click(screen.getByTestId(leadRowTestId));

    expect(onEditConcept).toHaveBeenCalledWith("n-plt");
    expect(onSelectNode).not.toHaveBeenCalled();
  });
});

describe("PathwayConditionsStage: editing an already-resolved DEMOGRAPHIC row", () => {
  const AGE_TEXT = "aged 55 or over";
  const AGE_BOUNDARY: PathwayTextBoundary[] = [
    { text: AGE_TEXT, start: 0, end: AGE_TEXT.length, source: "heuristic" },
  ];

  function ageLeaf(): EditableLogicNode {
    return { node_id: "age-1", kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 55, unit: "years" };
  }

  function AgeHarness({ onSelectNode = jest.fn() }: { onSelectNode?: (nodeId: string, anchor?: HTMLElement | null) => void }) {
    // The age leaf sits one level below the pathway AND (inside a
    // wrapping group), not as a direct pathway child, so it resolves
    // through the regular condition-row list (what this test targets)
    // rather than through PathwayDemographicsPanel's separate "direct
    // child" affordance -- the two are deliberately different surfaces.
    const [tree, setTree] = useState<EditableLogicNode>({
      node_id: "root",
      kind: "AND",
      children: [{ node_id: "wrap", kind: "AND", children: [ageLeaf()] }],
    });
    return (
      <PathwayConditionsStage
        tree={tree}
        recommendationText={AGE_TEXT}
        boundaries={AGE_BOUNDARY}
        pathwayIndex={0}
        clusterGroupings={{}}
        onSetClusterGrouping={jest.fn()}
        leadClusterGroupings={{}}
        onSetLeadClusterGrouping={jest.fn()}
        dismissedCopyAcrossOffers={new Set()}
        onDismissCopyAcrossOffer={jest.fn()}
        onSelectNode={onSelectNode}
        onUpdate={(update) => setTree((curr) => applyUpdate(curr, update) ?? curr)}
        onRequestAdd={jest.fn()}
        onEditConcept={jest.fn()}
        onConfirmPathway={jest.fn()}
      />
    );
  }

  it("toggles the inline age editor instead of calling onSelectNode", async () => {
    const user = userEvent.setup();
    const onSelectNode = jest.fn();
    render(<AgeHarness onSelectNode={onSelectNode} />);

    expect(screen.queryByLabelText(/how to compare age/i)).not.toBeInTheDocument();

    await user.click(screen.getByText(AGE_TEXT));
    expect(onSelectNode).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/how to compare age/i)).toBeInTheDocument();

    // Re-clicking the same row collapses the editor again.
    await user.click(screen.getByText(AGE_TEXT));
    expect(screen.queryByLabelText(/how to compare age/i)).not.toBeInTheDocument();
  });

  it("keeps the editor open and reflects operator changes even once the row's own wording no longer matches the guideline text verbatim", async () => {
    // Regression guard: the editor's node comes from a direct tree
    // lookup by node_id (see PathwayConditionsStage's
    // `expandedDemographicNode`), not from re-running the fuzzy
    // row<->text matcher on every render -- so it must not vanish just
    // because editing the value changes its own display text.
    const user = userEvent.setup();
    render(<AgeHarness />);

    await user.click(screen.getByText(AGE_TEXT));
    const operatorSelect = screen.getByLabelText(/how to compare age/i);
    expect(operatorSelect).toHaveTextContent(/is at least/i);

    await user.click(operatorSelect);
    await user.click(await screen.findByRole("option", { name: /is at most/i }));

    expect(screen.getByLabelText(/how to compare age/i)).toHaveTextContent(/is at most/i);
  });
});

describe("PathwayConditionsStage: editing an already-resolved OBSERVATION row", () => {
  const OBS_TEXT = "raised platelet count";
  const OBS_BOUNDARY: PathwayTextBoundary[] = [
    { text: OBS_TEXT, start: 0, end: OBS_TEXT.length, source: "heuristic" },
  ];

  function observationLeaf(): EditableLogicNode {
    return {
      node_id: "obs-1",
      kind: "OBSERVATION",
      // Pin the leaf to this row's guideline wording so resolution does
      // not depend on fuzzy overlap between "Platelet count" and
      // "raised platelet count".
      source_row_text: OBS_TEXT,
      observation: {
        observable_id: "365632008",
        observable_term: "Platelet count",
        operator: ">=",
        value: 400,
        unit: "10*9/L",
      },
    };
  }

  function ObsHarness({
    onSelectNode = jest.fn(),
    onEditConcept = jest.fn(),
  }: {
    onSelectNode?: (nodeId: string, anchor?: HTMLElement | null) => void;
    onEditConcept?: (nodeId: string) => void;
  }) {
    const [tree, setTree] = useState<EditableLogicNode>({
      node_id: "root",
      kind: "AND",
      children: [{ node_id: "wrap", kind: "AND", children: [observationLeaf()] }],
    });
    return (
      <PathwayConditionsStage
        tree={tree}
        recommendationText={OBS_TEXT}
        boundaries={OBS_BOUNDARY}
        pathwayIndex={0}
        clusterGroupings={{}}
        onSetClusterGrouping={jest.fn()}
        leadClusterGroupings={{}}
        onSetLeadClusterGrouping={jest.fn()}
        dismissedCopyAcrossOffers={new Set()}
        onDismissCopyAcrossOffer={jest.fn()}
        onSelectNode={onSelectNode}
        onUpdate={(update) => setTree((curr) => applyUpdate(curr, update) ?? curr)}
        onRequestAdd={jest.fn()}
        onEditConcept={onEditConcept}
        onConfirmPathway={jest.fn()}
      />
    );
  }

  it("routes a resolved OBSERVATION row to onEditConcept for threshold editing", async () => {
    const user = userEvent.setup();
    const onEditConcept = jest.fn();
    const onSelectNode = jest.fn();
    render(<ObsHarness onSelectNode={onSelectNode} onEditConcept={onEditConcept} />);

    await user.click(screen.getByText(OBS_TEXT));
    expect(onEditConcept).toHaveBeenCalledWith("obs-1");
    expect(onSelectNode).not.toHaveBeenCalled();
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
    // The trailing cluster's confirmed-grouping copy names the actual
    // findings ("Only one of weight loss, reflux, ... needs to match.")
    // rather than the generic "these" once terms are available -- see
    // `groupingConfirmedAtLeastN` in copy.ts -- so match either form.
    const leadGroup = screen.getByRole("group", { name: /nausea or vomiting/i });
    expect(within(leadGroup).getByText(/only one of .+ needs to match/i)).toBeInTheDocument();
    const trailingGroup = screen.getByRole("group", { name: /any of the following/i });
    expect(within(trailingGroup).getByText(/only one of .+ needs to match/i)).toBeInTheDocument();

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

  it("keeps a dismissal even if this stage unmounts and remounts, since the dismissal now lives one level up (wizard state)", async () => {
    // Mirrors HighlightWizard unmounting PathwayConditionsStage every
    // time `state.step` leaves "pathway-conditions" (e.g. Back to
    // Step 2, or forward to Review, then back again) -- before the
    // dismissal moved out of a local useState inside this component,
    // remounting it here would have silently resurfaced the offer.
    const user = userEvent.setup();
    function RemountableHarness() {
      const [mounted, setMounted] = useState(true);
      const [dismissedCopyAcrossOffers, setDismissedCopyAcrossOffers] = useState<Set<string>>(
        () => new Set(),
      );
      const [tree, setTree] = useState(buildInitialTree());
      return (
        <div>
          <button onClick={() => setMounted((m) => !m)}>Toggle mount</button>
          {mounted && (
            <PathwayConditionsStage
              tree={tree}
              recommendationText={TEXT}
              boundaries={BOUNDARIES}
              pathwayIndex={1}
              clusterGroupings={{ pw_a: "AT_LEAST" }}
              onSetClusterGrouping={jest.fn()}
              leadClusterGroupings={{}}
              onSetLeadClusterGrouping={jest.fn()}
              dismissedCopyAcrossOffers={dismissedCopyAcrossOffers}
              onDismissCopyAcrossOffer={(k) =>
                setDismissedCopyAcrossOffers((prev) => new Set(prev).add(k))
              }
              onSelectNode={jest.fn()}
              onUpdate={(update) => setTree((curr) => applyUpdate(curr, update) ?? curr)}
              onRequestAdd={jest.fn()}
              onEditConcept={jest.fn()}
              onConfirmPathway={jest.fn()}
            />
          )}
        </div>
      );
    }
    render(<RemountableHarness />);
    expect(screen.getByText(/situation a asked about the same 6 findings/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /i'll do this one myself/i }));
    expect(screen.queryByText(/situation a asked about the same/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /toggle mount/i }));
    await user.click(screen.getByRole("button", { name: /toggle mount/i }));

    expect(screen.queryByText(/situation a asked about the same/i)).not.toBeInTheDocument();
  });
});

describe("PathwayConditionsStage: invisible empty-group problems", () => {
  const SINGLE_TEXT = "raised platelet count with any of the following: nausea, vomiting.";
  const SINGLE_BOUNDARY: PathwayTextBoundary[] = [
    { text: SINGLE_TEXT, start: 0, end: SINGLE_TEXT.length, source: "heuristic" },
  ];

  /** A pathway with one resolved leaf plus a SECOND, abandoned
   *  AT_LEAST subgroup (e.g. the reviewer chose "only one needs to
   *  match" for a lead cluster, then never added anything to it and
   *  moved on) -- `buildPathwayRows(SINGLE_BOUNDARY)` has no row that
   *  would ever resolve to it, so without the fix it is permanently
   *  invisible even though it blocks Save. */
  function treeWithAbandonedCluster(): EditableLogicNode {
    return {
      node_id: "root",
      kind: "AND",
      children: [
        {
          node_id: "pw",
          kind: "AND",
          pathway_key: "pw",
          children: [
            concept("plt", "Raised platelet count"),
            {
              node_id: "abandoned-cluster",
              kind: "AT_LEAST",
              min: 1,
              cluster_role: "lead",
              children: [],
            },
          ],
        },
      ],
    };
  }

  function AbandonedClusterHarness() {
    const [tree, setTree] = useState(treeWithAbandonedCluster());
    return (
      <PathwayConditionsStage
        tree={tree}
        recommendationText={SINGLE_TEXT}
        boundaries={SINGLE_BOUNDARY}
        pathwayIndex={0}
        clusterGroupings={{}}
        onSetClusterGrouping={jest.fn()}
        leadClusterGroupings={{}}
        onSetLeadClusterGrouping={jest.fn()}
        dismissedCopyAcrossOffers={new Set()}
        onDismissCopyAcrossOffer={jest.fn()}
        onSelectNode={jest.fn()}
        onUpdate={(update) => setTree((curr) => applyUpdate(curr, update) ?? curr)}
        onRequestAdd={jest.fn()}
        onEditConcept={jest.fn()}
        onConfirmPathway={jest.fn()}
      />
    );
  }

  it("surfaces the abandoned empty subgroup as its own problem row", () => {
    render(<AbandonedClusterHarness />);
    expect(screen.getByTestId("wizard-problem-row-abandoned-cluster")).toBeInTheDocument();
    expect(screen.getByText(/match some of these.*empty/i)).toBeInTheDocument();
  });

  it("does not report the pathway's own in-progress emptiness as a separate problem", () => {
    // pw-b in the main fixture has zero children (situation B hasn't
    // been started) -- that must NOT also produce a
    // wizard-problem-row, since "N rows still need a code" already
    // covers it.
    render(<Harness pathwayIndex={1} />);
    expect(screen.queryByTestId("wizard-problem-row-pw-b")).not.toBeInTheDocument();
  });

  it("removes the abandoned subgroup via its Remove it action", async () => {
    const user = userEvent.setup();
    let latestTree: EditableLogicNode | undefined;
    function Harness2() {
      const [tree, setTree] = useState(treeWithAbandonedCluster());
      useEffect(() => {
        latestTree = tree;
      }, [tree]);
      return (
        <PathwayConditionsStage
          tree={tree}
          recommendationText={SINGLE_TEXT}
          boundaries={SINGLE_BOUNDARY}
          pathwayIndex={0}
          clusterGroupings={{}}
          onSetClusterGrouping={jest.fn()}
          leadClusterGroupings={{}}
          onSetLeadClusterGrouping={jest.fn()}
          dismissedCopyAcrossOffers={new Set()}
          onDismissCopyAcrossOffer={jest.fn()}
          onSelectNode={jest.fn()}
          onUpdate={(update) => setTree((curr) => applyUpdate(curr, update) ?? curr)}
          onRequestAdd={jest.fn()}
          onEditConcept={jest.fn()}
          onConfirmPathway={jest.fn()}
        />
      );
    }
    render(<Harness2 />);

    await user.click(screen.getByRole("button", { name: /remove this problem/i }));

    expect(latestTree?.children?.[0]?.children).toHaveLength(1);
    expect(screen.queryByTestId("wizard-problem-row-abandoned-cluster")).not.toBeInTheDocument();
  });
});

describe("PathwayConditionsStage: per-pathway demographics", () => {
  it("adds sex under the active pathway AND only", async () => {
    const user = userEvent.setup();
    let latestTree: EditableLogicNode | undefined;
    render(
      <Harness
        pathwayIndex={0}
        onTreeChange={(t) => {
          latestTree = t;
        }}
      />,
    );

    expect(screen.getByTestId("pathway-demographics-panel")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: /add a sex check for this situation only/i }),
    );

    const pwA = latestTree!.children![0].children![0];
    const pwB = latestTree!.children![0].children![1];
    expect(pwA.children!.some((c) => c.kind === "DEMOGRAPHIC" && c.field === "sex")).toBe(
      true,
    );
    expect(pwB.children!.some((c) => c.kind === "DEMOGRAPHIC")).toBe(false);
    expect(latestTree!.children!.filter((c) => c.kind === "DEMOGRAPHIC")).toHaveLength(0);
  });

  it("adds a lab value under the active pathway AND only", async () => {
    const user = userEvent.setup();
    let latestTree: EditableLogicNode | undefined;
    render(
      <Harness
        pathwayIndex={0}
        onTreeChange={(t) => {
          latestTree = t;
        }}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /add a lab value or reading for this situation only/i }),
    );

    const pwA = latestTree!.children![0].children![0];
    const pwB = latestTree!.children![0].children![1];
    expect(pwA.children!.some((c) => c.kind === "OBSERVATION")).toBe(true);
    expect(pwB.children!.some((c) => c.kind === "OBSERVATION")).toBe(false);
  });

  it("blocks Confirm when a pathway age value is cleared", async () => {
    const user = userEvent.setup();
    render(<Harness pathwayIndex={0} />);

    await user.click(
      screen.getByRole("button", { name: /add an age check for this situation only/i }),
    );
    const ageInput = screen.getByLabelText(/^lower bound$/i);
    await user.clear(ageInput);

    expect(screen.getByRole("button", { name: /confirm situation a/i })).toBeDisabled();
    expect(screen.getByText(/add a number for this patient detail/i)).toBeInTheDocument();
  });
});

// NG12 1.3.1 regression: when the guideline sentence cannot be split
// into exactly as many text boundaries as saved pathways, the wizard
// falls back to `boundary.source === "tree"` for every situation
// (see `boundariesFromPathways`) -- which means `buildPathwayRows`
// returns no text rows at all. Before this fix, a bare-leaf pathway
// (situation A, "abdominal mass" with no AND wrapper) or a
// multi-concept AND pathway (situation D, age + two findings) had
// nothing rendering their own already-captured CONCEPT leaves: only
// PathwayDemographicsPanel's age/sex band showed up, so the actual
// clinical finding(s) silently vanished from Step 3 even though
// Review's plain-English summary rendered them correctly.
describe("PathwayConditionsStage: tree-rehydrated confirmed conditions", () => {
  const TREE_BOUNDARIES: PathwayTextBoundary[] = [
    { text: "has abdominal mass", start: 0, end: 0, source: "tree" },
    { text: "is 40 years or older, weight loss, abdominal pain", start: 0, end: 0, source: "tree" },
  ];

  function buildTreeSourcedTree(): EditableLogicNode {
    return {
      node_id: "root",
      kind: "OR",
      children: [
        // Situation A: a bare CONCEPT leaf with no AND wrapper.
        concept("mass", "Abdominal mass"),
        // Situation B: an AND group with an age check plus two findings.
        {
          node_id: "pw-b",
          kind: "AND",
          pathway_key: "pw_b",
          children: [
            { node_id: "age", kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: "40" },
            concept("wl", "Weight loss"),
            concept("ap", "Abdominal pain"),
          ],
        },
      ],
    };
  }

  function TreeHarness({
    pathwayIndex,
    onEditConcept = jest.fn(),
    onTreeChange,
  }: {
    pathwayIndex: number;
    onEditConcept?: (nodeId: string) => void;
    onTreeChange?: (tree: EditableLogicNode) => void;
  }) {
    const [tree, setTree] = useState(buildTreeSourcedTree());
    useEffect(() => {
      onTreeChange?.(tree);
    }, [tree, onTreeChange]);
    return (
      <PathwayConditionsStage
        tree={tree}
        recommendationText="1.3.1 has abdominal mass, or is 40 years or older, weight loss, abdominal pain."
        boundaries={TREE_BOUNDARIES}
        pathwayIndex={pathwayIndex}
        clusterGroupings={{}}
        onSetClusterGrouping={jest.fn()}
        leadClusterGroupings={{}}
        onSetLeadClusterGrouping={jest.fn()}
        dismissedCopyAcrossOffers={new Set()}
        onDismissCopyAcrossOffer={jest.fn()}
        onSelectNode={jest.fn()}
        onUpdate={(update) => setTree((curr) => applyUpdate(curr, update) ?? curr)}
        onRequestAdd={jest.fn()}
        onEditConcept={onEditConcept}
        onConfirmPathway={jest.fn()}
      />
    );
  }

  it("shows a bare-leaf pathway's own concept as a confirmed condition", async () => {
    const user = userEvent.setup();
    const onEditConcept = jest.fn();
    render(<TreeHarness pathwayIndex={0} onEditConcept={onEditConcept} />);

    const row = screen.getByTestId("pathway-confirmed-condition-n-mass");
    expect(within(row).getByText(/abdominal mass/i)).toBeInTheDocument();

    // A bare leaf has no AND wrapper to leave siblings behind in, so
    // removal is not offered -- deleting it would silently delete the
    // whole situation.
    expect(within(row).queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();

    await user.click(within(row).getByText(/abdominal mass/i));
    expect(onEditConcept).toHaveBeenCalledWith("n-mass");
  });

  it("lists every non-demographic leaf of a multi-concept AND pathway and allows removing one", async () => {
    const user = userEvent.setup();
    let latestTree: EditableLogicNode | undefined;
    render(
      <TreeHarness
        pathwayIndex={1}
        onTreeChange={(t) => {
          latestTree = t;
        }}
      />,
    );

    expect(screen.getByTestId("pathway-confirmed-condition-n-wl")).toBeInTheDocument();
    expect(screen.getByTestId("pathway-confirmed-condition-n-ap")).toBeInTheDocument();
    // The age DEMOGRAPHIC leaf is excluded here -- it already renders
    // via PathwayDemographicsPanel instead.
    expect(screen.queryByTestId("pathway-confirmed-condition-age")).not.toBeInTheDocument();
    expect(screen.getByTestId("pathway-demographics-panel")).toBeInTheDocument();

    const weightLossRow = screen.getByTestId("pathway-confirmed-condition-n-wl");
    await user.click(within(weightLossRow).getByRole("button", { name: /remove/i }));

    const pwB = latestTree!.children![1];
    expect(pwB.children!.some((c) => c.node_id === "n-wl")).toBe(false);
    expect(pwB.children!.some((c) => c.node_id === "n-ap")).toBe(true);
    expect(pwB.children!.some((c) => c.kind === "DEMOGRAPHIC")).toBe(true);
  });
});

// Sibling of the tree-rehydrated suite above: when boundaries ARE
// heuristic/structure (so text rows exist) but a CONCEPT leaf on the
// pathway never matched any row -- e.g. authored via Advanced/Sentence
// with a preferred term that shares no wording with the guideline --
// Step 3 must still surface that leaf as a confirmed condition rather
// than silently hiding it behind the "only show confirmedLeaves when
// source === tree" gate.
describe("PathwayConditionsStage: orphan tree leaves on text-derived boundaries", () => {
  const HEURISTIC_TEXT = "weight loss or abdominal pain.";
  const HEURISTIC_BOUNDARIES: PathwayTextBoundary[] = [
    {
      text: HEURISTIC_TEXT,
      start: 0,
      end: HEURISTIC_TEXT.length,
      source: "heuristic",
    },
  ];

  function buildOrphanLeafTree(): EditableLogicNode {
    return {
      node_id: "root",
      kind: "AND",
      children: [
        {
          node_id: "pw-a",
          kind: "AND",
          pathway_key: "pw_a",
          children: [
            // Matches a guideline row via preferred-term wording.
            concept("wl", "Weight loss"),
            // Shares no words with the guideline text and has no
            // source_row_text -- would never resolve onto a row.
            {
              node_id: "n-orphan",
              kind: "CONCEPT",
              criterion: {
                snomed_concept_id: "999",
                preferred_term: "Raised platelet count",
              },
            },
          ],
        },
      ],
    };
  }

  it("shows an unmatched CONCEPT leaf as a confirmed condition alongside the text rows", () => {
    render(
      <PathwayConditionsStage
        tree={buildOrphanLeafTree()}
        recommendationText={HEURISTIC_TEXT}
        boundaries={HEURISTIC_BOUNDARIES}
        pathwayIndex={0}
        clusterGroupings={{}}
        onSetClusterGrouping={jest.fn()}
        leadClusterGroupings={{}}
        onSetLeadClusterGrouping={jest.fn()}
        dismissedCopyAcrossOffers={new Set()}
        onDismissCopyAcrossOffer={jest.fn()}
        onSelectNode={jest.fn()}
        onUpdate={jest.fn()}
        onRequestAdd={jest.fn()}
        onEditConcept={jest.fn()}
        onConfirmPathway={jest.fn()}
      />,
    );

    const orphan = screen.getByTestId("pathway-confirmed-condition-n-orphan");
    expect(within(orphan).getByText(/raised platelet count/i)).toBeInTheDocument();
    // The matched leaf must NOT also appear in the confirmed list --
    // that would duplicate the text row it already resolves onto.
    expect(screen.queryByTestId("pathway-confirmed-condition-n-wl")).not.toBeInTheDocument();
  });
});
