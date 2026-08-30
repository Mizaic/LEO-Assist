/**
 * Group mode (AND / OR / AT_LEAST) must be an explicit labelled
 * choice. NICE "or" lists must not silently save as AND.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339 / VT-8AF20438
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { GROUP_KIND_LABELS, GROUP_KIND_SHORT } from "../copy";
import { ClusterGroupingChoice } from "../HighlightWizard/PathwayConditionsChrome";
import {
  buildPathwayRows,
  withReifiedPathwayClusters,
} from "../HighlightWizard/wizardMapping";
import { STEP_PATHWAY_CONDITIONS } from "../HighlightWizard/copy";
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import { applyUpdate, assignNodeIds, stripNodeIds } from "../treeOps";
import type { EditableLogicNode } from "../types";

const NG12_1517_OR_LIST = "vulval lump, ulceration or bleeding";

const NG12_1517_BOUNDARY: PathwayTextBoundary = {
  text: NG12_1517_OR_LIST,
  start: 0,
  end: NG12_1517_OR_LIST.length,
  source: "heuristic",
};

function concept(
  id: string,
  term: string,
  sourceRowText: string,
): EditableLogicNode {
  return {
    node_id: id,
    kind: "CONCEPT",
    source_row_text: sourceRowText,
    criterion: { snomed_concept_id: id, preferred_term: term },
  };
}

function threeFindingAndPathway(): EditableLogicNode {
  return {
    node_id: "pw-a",
    kind: "AND",
    pathway_key: "pw_a",
    children: [
      concept("1", "Vulval lump", "vulval lump"),
      concept("2", "Ulceration", "ulceration"),
      concept("3", "Bleeding", "bleeding"),
    ],
  };
}

function treeWithPathway(pathway: EditableLogicNode): EditableLogicNode {
  return {
    node_id: "root",
    kind: "AND",
    children: [{ node_id: "or", kind: "OR", children: [pathway] }],
  };
}

describe("Group mode labels name AND, OR, and AT LEAST", () => {
  it("AND is a labelled option, not only a hidden default", () => {
    expect(GROUP_KIND_LABELS.AND).toMatch(/\bAND\b/);
    expect(GROUP_KIND_SHORT.AND).toMatch(/\bAND\b/);
    expect(STEP_PATHWAY_CONDITIONS.allMustMatchLabel).toMatch(/\bAND\b/);
  });

  it("OR and AT LEAST are labelled options too", () => {
    expect(GROUP_KIND_LABELS.OR).toMatch(/\bOR\b/);
    expect(GROUP_KIND_SHORT.OR).toMatch(/\bOR\b/);
    expect(STEP_PATHWAY_CONDITIONS.onlyOneLabel(true)).toMatch(/\bOR\b/);
    expect(STEP_PATHWAY_CONDITIONS.atLeastNLabel(2, true)).toMatch(/AT LEAST/i);
  });
});

describe("ClusterGroupingChoice: author can set AND or OR", () => {
  it("shows labelled AND and OR buttons before a choice", () => {
    render(
      <ClusterGroupingChoice
        prompt="How should these findings match?"
        onChoose={jest.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: /\bAND\b/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /\bOR\b/i }),
    ).toBeInTheDocument();
  });

  it("calls onChoose with OR when the author picks OR", async () => {
    const user = userEvent.setup();
    const onChoose = jest.fn();
    render(
      <ClusterGroupingChoice
        prompt="How should these findings match?"
        onChoose={onChoose}
      />,
    );

    await user.click(screen.getByRole("button", { name: /\bOR\b/i }));
    expect(onChoose.mock.calls[0][0]).toBe("OR");
  });

  it("calls onChoose with AND when the author picks AND", async () => {
    const user = userEvent.setup();
    const onChoose = jest.fn();
    render(
      <ClusterGroupingChoice
        prompt="How should these findings match?"
        onChoose={onChoose}
      />,
    );

    await user.click(screen.getByRole("button", { name: /\bAND\b/i }));
    expect(onChoose).toHaveBeenCalledWith("AND");
  });

  it("Change re-shows labelled AND and OR instead of silently toggling", async () => {
    const user = userEvent.setup();
    const onChoose = jest.fn();
    render(
      <ClusterGroupingChoice
        prompt="How should these findings match?"
        grouping="OR"
        onChoose={onChoose}
      />,
    );

    await user.click(screen.getByRole("button", { name: /change/i }));
    expect(onChoose).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: /\bAND\b/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /\bOR\b/i }),
    ).toBeInTheDocument();
  });
});

describe("NICE or-list: three findings do not serialise as AND", () => {
  it("treats a marker-less 'A, B or C' list as a group that needs a mode", () => {
    const rows = buildPathwayRows(NG12_1517_BOUNDARY);
    expect(rows.hasCluster).toBe(true);
    expect(rows.items.map((item) => item.text)).toEqual([
      "vulval lump",
      "ulceration",
      "bleeding",
    ]);
  });

  it("saves kind OR when the author chooses OR for a three-finding NICE or list", () => {
    const tree = treeWithPathway(threeFindingAndPathway());
    const next = withReifiedPathwayClusters(
      tree,
      "pw-a",
      NG12_1517_BOUNDARY,
      "OR",
      undefined,
    );
    const pathway = next.children![0].children![0];
    const group = pathway.children![0];
    expect(group.kind).toBe("OR");
    expect(group.children).toHaveLength(3);
    expect(stripNodeIds(group).kind).toBe("OR");
    expect(stripNodeIds(group).kind).not.toBe("AND");
  });

  it("keeps kind AND / OR / AT_LEAST on change_kind and save", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "A" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "B" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "3", preferred_term: "C" } },
      ],
    });

    const asOr = applyUpdate(tree, {
      kind: "change_kind",
      nodeId: tree.node_id,
      newKind: "OR",
    });
    expect(stripNodeIds(asOr!).kind).toBe("OR");

    const asAnd = applyUpdate(asOr!, {
      kind: "change_kind",
      nodeId: tree.node_id,
      newKind: "AND",
    });
    expect(stripNodeIds(asAnd!).kind).toBe("AND");

    const asAtLeast = applyUpdate(asAnd!, {
      kind: "change_kind",
      nodeId: tree.node_id,
      newKind: "AT_LEAST",
    });
    expect(stripNodeIds(asAtLeast!).kind).toBe("AT_LEAST");
  });
});
