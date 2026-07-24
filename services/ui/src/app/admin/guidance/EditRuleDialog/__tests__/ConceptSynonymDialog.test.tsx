/**
 * Live-render tests for ConceptSynonymDialog -- the add/remove/depth
 * editor for a CONCEPT leaf's synonym set (UN-LEO-AI-093 /
 * DI-LEO-AI-511), extracted out of SynonymChipEditor so it can be
 * opened straight from a node_id (no chip UI required), which is
 * exactly what the highlight-to-build wizard's "edit an existing
 * pick" flow needs.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ConceptSynonymDialog, {
  deriveSynonymEditorState,
} from "../ConceptSynonymDialog";
import type { EditableLogicNode, NodeUpdate } from "../types";

function makeLeaf(overrides: Partial<EditableLogicNode["criterion"]> = {}): EditableLogicNode {
  return {
    node_id: "leaf-1",
    kind: "CONCEPT",
    criterion: {
      snomed_concept_id: "162031009",
      preferred_term: "Indigestion",
      semantic_tag: "finding",
      ...overrides,
    },
  };
}

function mockSearch(hits: unknown[]) {
  (global.fetch as jest.Mock).mockImplementation((url: string) => {
    if (String(url).includes("/api/terminology/search")) {
      return Promise.resolve({
        ok: true,
        json: async () => hits,
      });
    }
    return Promise.resolve({ ok: true, json: async () => [] });
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("deriveSynonymEditorState", () => {
  it("promotes a legacy single-code criterion into a one-seed set", () => {
    const { seeds, excluded, primaryId } = deriveSynonymEditorState(
      makeLeaf().criterion,
    );
    expect(seeds).toEqual([
      expect.objectContaining({
        snomed_concept_id: "162031009",
        preferred_term: "Indigestion",
        include_descendants: true,
      }),
    ]);
    expect(excluded).toEqual([]);
    expect(primaryId).toBe("162031009");
  });

  it("passes through an already-populated synonym set unchanged", () => {
    const criterion = {
      snomed_concept_id: "162031009",
      preferred_term: "Indigestion",
      seeds: [
        { snomed_concept_id: "162031009", preferred_term: "Indigestion" },
        { snomed_concept_id: "1683081000119100", preferred_term: "Dyspepsia" },
      ],
      excluded_concept_ids: ["999"],
      primary_concept_id: "1683081000119100",
    };
    const { seeds, excluded, primaryId } = deriveSynonymEditorState(criterion);
    expect(seeds).toHaveLength(2);
    expect(excluded).toEqual(["999"]);
    expect(primaryId).toBe("1683081000119100");
  });

  it("returns an empty seed set for an unset criterion (no code yet)", () => {
    const { seeds, primaryId } = deriveSynonymEditorState(undefined);
    expect(seeds).toEqual([]);
    expect(primaryId).toBe("");
  });
});

describe("ConceptSynonymDialog: rendering", () => {
  it("renders nothing when node is null", () => {
    render(
      <ConceptSynonymDialog open node={null} onUpdate={jest.fn()} onClose={jest.fn()} />,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the existing code and marks it as the chip label", () => {
    render(
      <ConceptSynonymDialog
        open
        node={makeLeaf()}
        onUpdate={jest.fn()}
        onClose={jest.fn()}
      />,
    );
    expect(screen.getByText(/edit .indigestion./i)).toBeInTheDocument();
    expect(screen.getByText(/code 162031009/)).toBeInTheDocument();
    expect(screen.getByText("Label")).toBeInTheDocument();
  });

  it("disables Remove when there is only one code and clear-match is not offered", () => {
    render(
      <ConceptSynonymDialog
        open
        node={makeLeaf()}
        onUpdate={jest.fn()}
        onClose={jest.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /remove indigestion from this chip/i }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: /remove this match/i }),
    ).not.toBeInTheDocument();
  });

  it("lets the wizard undo a mistaken pick via Remove this match", async () => {
    const user = userEvent.setup();
    const onClearMatch = jest.fn();
    render(
      <ConceptSynonymDialog
        open
        node={makeLeaf()}
        onUpdate={jest.fn()}
        onClose={jest.fn()}
        onClearMatch={onClearMatch}
      />,
    );

    await user.click(screen.getByRole("button", { name: /remove this match/i }));
    expect(onClearMatch).toHaveBeenCalledTimes(1);
  });

  it("lets the wizard clear the last code via the row X (same as Remove this match)", async () => {
    const user = userEvent.setup();
    const onClearMatch = jest.fn();
    render(
      <ConceptSynonymDialog
        open
        node={makeLeaf()}
        onUpdate={jest.fn()}
        onClose={jest.fn()}
        onClearMatch={onClearMatch}
      />,
    );

    await user.click(screen.getByRole("button", { name: /remove match for indigestion/i }));
    expect(onClearMatch).toHaveBeenCalledTimes(1);
  });
});

describe("ConceptSynonymDialog: add a code", () => {
  it("adds a second code via search, defaulting it to exact-match-only", async () => {
    const user = userEvent.setup();
    mockSearch([
      { snomed_concept_id: "1683081000119100", term: "Dyspepsia", semantic_tag: "finding" },
    ]);
    const onUpdate = jest.fn();
    render(
      <ConceptSynonymDialog
        open
        node={makeLeaf()}
        onUpdate={onUpdate}
        onClose={jest.fn()}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /add another code that means the same/i }),
    );
    fireEvent.change(screen.getByLabelText("Search clinical terms"), {
      target: { value: "dyspepsia" },
    });
    // The row's `aria-label` ("Use Dyspepsia") overrides the button's
    // visible text ("Use this") as its accessible name, so the query
    // must match the label, not the on-screen copy.
    const useThisButton = await waitFor(
      () => screen.getByRole("button", { name: "Use Dyspepsia" }),
      { timeout: 3000 },
    );
    await user.click(useThisButton);

    expect(onUpdate).toHaveBeenCalledWith({
      kind: "add_seed",
      nodeId: "leaf-1",
      seed: {
        snomed_concept_id: "1683081000119100",
        preferred_term: "Dyspepsia",
        semantic_tag: "finding",
        include_descendants: false,
      },
    });
  });
});

describe("ConceptSynonymDialog: manage an existing multi-code set", () => {
  function twoSeedLeaf(): EditableLogicNode {
    return {
      node_id: "leaf-2",
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "162031009",
        preferred_term: "Indigestion",
        seeds: [
          { snomed_concept_id: "162031009", preferred_term: "Indigestion", include_descendants: true },
          {
            snomed_concept_id: "1683081000119100",
            preferred_term: "Dyspepsia",
            include_descendants: false,
          },
        ],
        primary_concept_id: "162031009",
        excluded_concept_ids: [],
      },
    };
  }

  it("removes a code when there is more than one", async () => {
    const user = userEvent.setup();
    const onUpdate = jest.fn();
    render(
      <ConceptSynonymDialog
        open
        node={twoSeedLeaf()}
        onUpdate={onUpdate}
        onClose={jest.fn()}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /remove dyspepsia from this chip/i }),
    );

    expect(onUpdate).toHaveBeenCalledWith({
      kind: "remove_seed",
      nodeId: "leaf-2",
      conceptId: "1683081000119100",
    });
  });

  it("switches the chip label to a different seed via its radio", async () => {
    const user = userEvent.setup();
    const onUpdate = jest.fn();
    render(
      <ConceptSynonymDialog
        open
        node={twoSeedLeaf()}
        onUpdate={onUpdate}
        onClose={jest.fn()}
      />,
    );

    await user.click(
      screen.getByRole("radio", { name: /use dyspepsia as the chip label/i }),
    );

    expect(onUpdate).toHaveBeenCalledWith({
      kind: "set_primary_seed",
      nodeId: "leaf-2",
      conceptId: "1683081000119100",
    });
  });

  it("turns on descendant expansion for a seed that starts as exact-match-only", async () => {
    const user = userEvent.setup();
    const onUpdate = jest.fn();
    render(
      <ConceptSynonymDialog
        open
        node={twoSeedLeaf()}
        onUpdate={onUpdate}
        onClose={jest.fn()}
      />,
    );

    await user.click(
      screen.getByRole("switch", { name: /include descendants for dyspepsia/i }),
    );

    expect(onUpdate).toHaveBeenCalledWith({
      kind: "toggle_include_descendants",
      nodeId: "leaf-2",
      conceptId: "1683081000119100",
    });
  });

  it("sets an explicit depth for a seed that already has descendants on", async () => {
    const user = userEvent.setup();
    const onUpdate = jest.fn();
    render(
      <ConceptSynonymDialog
        open
        node={twoSeedLeaf()}
        onUpdate={onUpdate}
        onClose={jest.fn()}
      />,
    );

    const depthField = screen.getByLabelText(/descendant depth for indigestion/i);
    await user.clear(depthField);
    await user.type(depthField, "2");

    expect(onUpdate).toHaveBeenCalledWith({
      kind: "set_seed_distance",
      nodeId: "leaf-2",
      conceptId: "162031009",
      distance: 2,
    });
  });
});

describe("ConceptSynonymDialog: closing", () => {
  it("calls onClose when Done is clicked", async () => {
    const user = userEvent.setup();
    const onClose = jest.fn();
    render(
      <ConceptSynonymDialog open node={makeLeaf()} onUpdate={jest.fn()} onClose={onClose} />,
    );

    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose from the header close icon too", async () => {
    const user = userEvent.setup();
    const onClose = jest.fn();
    render(
      <ConceptSynonymDialog open node={makeLeaf()} onUpdate={jest.fn()} onClose={onClose} />,
    );

    await user.click(screen.getByRole("button", { name: /close synonym editor/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("ConceptSynonymDialog: dialog chrome sanity", () => {
  it("uses the dialog's own title element, not a stray duplicate", () => {
    render(
      <ConceptSynonymDialog open node={makeLeaf()} onUpdate={jest.fn()} onClose={jest.fn()} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/edit .indigestion./i)).toBeInTheDocument();
  });
});
