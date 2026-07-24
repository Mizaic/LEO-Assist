/**
 * Phase 2 integration tests for EditRuleDialog -- VT-LEO-AI-152.
 *
 * Covers:
 *   - Plain-English summary card renders at the top of the dialog and
 *     updates as the tree changes.
 *   - Vague phrases like "Symptoms of lung cancer" surface a yellow
 *     lightbulb badge next to the chip.
 *   - Clicking the lightbulb opens the Concept Coach popover with
 *     curated suggestions for the captured topic.
 *   - "Add ticked" inserts the chosen suggestions as siblings.
 *   - "Replace vague phrase" inserts suggestions and removes the vague
 *     chip from the saved tree.
 */

import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

import EditRuleDialog from "..";

const VAGUE_RULE = {
  rule_id: "rule:NG12:lung-vague",
  name: "Lung cancer red flags",
  strength: "refer",
  guideline_id: "NG12",
  chapter_title: "Lung and pleural cancers",
  recommendation_text:
    "Refer for chest X-ray within 2 weeks if symptoms of lung cancer.",
  logic_tree: {
    kind: "AND",
    children: [
      {
        kind: "DEMOGRAPHIC",
        field: "age",
        operator: ">=",
        value: 40,
        unit: "years",
      },
      {
        kind: "CONCEPT",
        criterion: {
          snomed_concept_id: "vague:lung",
          preferred_term: "Symptoms of lung cancer",
        },
      },
    ],
  },
};

function mockSearch(hits: unknown[] = []) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).includes("/api/terminology/search")) {
      return Promise.resolve({
        ok: true,
        json: async () => hits,
        text: async () => JSON.stringify(hits),
      } as Response);
    }
    return Promise.resolve({
      ok: true,
      json: async () => [],
      text: async () => "[]",
    } as Response);
  });
}

/**
 * The widescreen editor splits the form across three steps. The
 * reason field lives on step 3 ("Save your change").
 */
function fillReason(text: string) {
  const rail = screen.getAllByRole("button", {
    name: /^Step 3 of 3/i,
  });
  fireEvent.click(rail[0]);
  fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
    target: { value: text },
  });
}

const VIEW_MODE_STORAGE_KEY = "leo.editRuleDialog.viewMode";

beforeEach(() => {
  // The Concept Coach lightbulb only exists on the Advanced tree
  // canvas (LogicTreeEditor/ConceptPill.tsx) -- it was never ported to
  // the Simple sentence canvas either. Guided is now the default
  // view, so force Advanced explicitly rather than relying on a
  // default that no longer lands here.
  window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, "advanced");
});

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
});

describe("EditRuleDialog phase 3 (always-visible LivePreviewPane)", () => {
  it("renders the always-visible Live preview pane with the rule summary in plain English", () => {
    // Phase 3 layout: the LivePreviewBanner + LivePreviewDrawer toggle
    // was deleted. The plain-English summary now lives in an
    // always-visible right-hand pane (~40% wide) so a reviewer can
    // always see what the rule means while editing.
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    const pane = screen.getByRole("region", {
      name: /live preview of this rule/i,
    });
    expect(pane).toBeInTheDocument();
    expect(within(pane).getByText(/40 years or older/i)).toBeInTheDocument();
    expect(within(pane).getByText(/symptoms of lung cancer/i)).toBeInTheDocument();
  });

  it("Live preview pane shows 'What the system will do' alongside the summary", () => {
    // The pane stacks the SummaryCard and the SystemRecap so the
    // reviewer always knows both the precondition (who matches) and
    // the resulting action.
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    const pane = screen.getByRole("region", {
      name: /live preview of this rule/i,
    });
    expect(
      within(pane).getByRole("region", {
        name: /what the system will do when this rule matches/i,
      }),
    ).toBeInTheDocument();
  });

  it("shows a vague-phrase lightbulb badge next to the vague chip", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    expect(
      screen.getByRole("button", {
        name: /get specific suggestions for "symptoms of lung cancer"/i,
      }),
    ).toBeInTheDocument();
  });

  it("opens the Coach popover when the lightbulb is clicked", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: /get specific suggestions for "symptoms of lung cancer"/i,
      }),
    );
    const popover = screen.getByRole("presentation");
    expect(within(popover).getByText(/this phrase is vague/i)).toBeInTheDocument();
    expect(within(popover).getByText(/symptoms of lung cancer/i)).toBeInTheDocument();
    // Cough and Haemoptysis come from the curated lung-cancer list.
    expect(within(popover).getByLabelText(/add cough/i)).toBeInTheDocument();
    expect(within(popover).getByLabelText(/add haemoptysis/i)).toBeInTheDocument();
  });

  it("'Add ticked' inserts the picked suggestions as siblings of the vague chip", async () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={onSave} />,
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: /get specific suggestions for "symptoms of lung cancer"/i,
      }),
    );
    fireEvent.click(screen.getByLabelText(/add cough/i));
    fireEvent.click(screen.getByLabelText(/add haemoptysis/i));
    fireEvent.click(
      screen.getByRole("button", {
        name: /add the ticked symptoms next to the vague phrase/i,
      }),
    );
    fillReason("Made the lung cancer phrase concrete");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const tree = onSave.mock.calls[0][0].logic_tree;
    const concepts = (tree.children as Array<{ kind: string; criterion?: { snomed_concept_id: string } }>)
      .filter((c) => c.kind === "CONCEPT")
      .map((c) => c.criterion?.snomed_concept_id);
    expect(concepts).toEqual(
      expect.arrayContaining(["vague:lung", "49727002", "66857006"]),
    );
  });

  it("'Replace vague phrase' inserts suggestions and removes the original vague chip", async () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={onSave} />,
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: /get specific suggestions for "symptoms of lung cancer"/i,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /tick every suggestion/i }));
    fireEvent.click(
      screen.getByRole("button", {
        name: /replace the vague phrase with the ticked symptoms/i,
      }),
    );
    fillReason("Replaced vague phrase with NICE NG12 specifics");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const tree = onSave.mock.calls[0][0].logic_tree;
    const concepts = (tree.children as Array<{ kind: string; criterion?: { snomed_concept_id: string } }>)
      .filter((c) => c.kind === "CONCEPT")
      .map((c) => c.criterion?.snomed_concept_id);
    expect(concepts).not.toContain("vague:lung");
    expect(concepts).toEqual(expect.arrayContaining(["49727002", "66857006"]));
  });

  it("'Search for more' opens the search panel with the topic pre-filled", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: /get specific suggestions for "symptoms of lung cancer"/i,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /search for more/i }));
    const search = screen.getByLabelText(/search clinical terms/i) as HTMLInputElement;
    expect(search).toBeInTheDocument();
    expect(search.value).toBe("lung cancer");
  });
});
