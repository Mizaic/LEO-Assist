/**
 * Live-render tests for editing linked guideline wording inside
 * ConceptSynonymDialog -- lets a reviewer click disconnected words in
 * the NICE recommendation (e.g. "unexplained" + "vulval" + "bleeding."
 * on NG12 1.5.17) on an already-captured condition without deleting
 * and re-adding the leaf.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ConceptSynonymDialog from "../ConceptSynonymDialog";
import type { EditableLogicNode } from "../types";

const NG12_1517 =
  "1.5.17 Consider a suspected cancer pathway referral for vulval cancer in women, and trans men and non-binary people with female reproductive organs who have an unexplained vulval lump, ulceration or bleeding. [2015]";

function makeBleedingLeaf(sourceRowText?: string): EditableLogicNode {
  return {
    node_id: "leaf-bleed",
    kind: "CONCEPT",
    ...(sourceRowText ? { source_row_text: sourceRowText } : {}),
    criterion: {
      snomed_concept_id: "890094005",
      preferred_term: "Bleeding from genital region (finding)",
      semantic_tag: "finding",
      seeds: [
        {
          snomed_concept_id: "890094005",
          preferred_term: "Bleeding from genital region (finding)",
          semantic_tag: "finding",
          include_descendants: false,
        },
      ],
    },
  };
}

describe("ConceptSynonymDialog: Guideline wording panel", () => {
  it("hides the guideline wording panel when recommendationText is omitted", () => {
    render(
      <ConceptSynonymDialog
        open
        node={makeBleedingLeaf("bleeding.")}
        onUpdate={jest.fn()}
        onClose={jest.fn()}
      />,
    );

    expect(screen.queryByText(/guideline wording/i)).not.toBeInTheDocument();
  });

  it("shows existing source_row_text and lets the reviewer pick disconnected words from the NICE quote", async () => {
    const user = userEvent.setup();
    const onUpdate = jest.fn();

    render(
      <ConceptSynonymDialog
        open
        node={makeBleedingLeaf("bleeding.")}
        recommendationText={NG12_1517}
        onUpdate={onUpdate}
        onClose={jest.fn()}
      />,
    );

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/guideline wording/i)).toBeInTheDocument();
    expect(within(dialog).getByText("bleeding.")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /change wording/i }));

    // Click "unexplained", the second "vulval" ("vulval lump,"), and "bleeding."
    await user.click(within(dialog).getByText("unexplained", { selector: "[data-word-index]" }));
    const vulvalChunks = within(dialog).getAllByText("vulval", { selector: "[data-word-index]" });
    await user.click(vulvalChunks[vulvalChunks.length - 1]);
    await user.click(within(dialog).getByText("bleeding.", { selector: "[data-word-index]" }));

    await user.click(within(dialog).getByRole("button", { name: /confirm selection/i }));

    expect(onUpdate).toHaveBeenCalledWith({
      kind: "set_source_row_text",
      nodeId: "leaf-bleed",
      sourceRowText: "unexplained vulval bleeding.",
    });
  });

  it("lets the reviewer reset custom guideline wording back to code name", async () => {
    const user = userEvent.setup();
    const onUpdate = jest.fn();

    render(
      <ConceptSynonymDialog
        open
        node={makeBleedingLeaf("unexplained vulval bleeding.")}
        recommendationText={NG12_1517}
        onUpdate={onUpdate}
        onClose={jest.fn()}
      />,
    );

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /reset to code name/i }));

    expect(onUpdate).toHaveBeenCalledWith({
      kind: "set_source_row_text",
      nodeId: "leaf-bleed",
      sourceRowText: null,
    });
  });
});
