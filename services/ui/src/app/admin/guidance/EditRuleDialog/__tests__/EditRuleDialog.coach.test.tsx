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
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

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

afterEach(() => {
  jest.restoreAllMocks();
});

describe("EditRuleDialog phase 2", () => {
  it("renders the plain-English summary card at the top", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    const summary = screen.getByRole("region", {
      name: /plain english summary of this rule/i,
    });
    expect(summary).toBeInTheDocument();
    expect(within(summary).getByText(/what this rule means/i)).toBeInTheDocument();
    expect(within(summary).getByText(/40 years or older/i)).toBeInTheDocument();
    expect(within(summary).getByText(/symptoms of lung cancer/i)).toBeInTheDocument();
  });

  it("collapses the summary body when the toggle is clicked and reopens it", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    const summary = screen.getByRole("region", {
      name: /plain english summary of this rule/i,
    });
    const toggle = within(summary).getByRole("button", {
      name: /hide plain english summary/i,
    });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAttribute("aria-controls");
    const bodyId = toggle.getAttribute("aria-controls")!;
    const body = document.getElementById(bodyId);
    expect(body).not.toBeNull();
    expect(within(body!).getByText(/40 years or older/i)).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAccessibleName(/show plain english summary/i);

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAccessibleName(/hide plain english summary/i);
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
    fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
      target: { value: "Made the lung cancer phrase concrete" },
    });
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
    fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
      target: { value: "Replaced vague phrase with NICE NG12 specifics" },
    });
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
