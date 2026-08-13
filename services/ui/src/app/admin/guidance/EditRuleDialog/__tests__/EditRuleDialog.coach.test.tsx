/**
 * Phase 2/3 integration tests for EditRuleDialog -- VT-LEO-AI-152.
 *
 * Covers the always-visible right-column preview once Guided is past
 * the quote-pinned build steps. Concept Coach (vague-phrase lightbulb)
 * lived on the removed Advanced ConceptPill canvas and is not yet
 * ported to Guided -- those cases are skipped until that port lands.
 */

import React from "react";
import {
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";

import EditRuleDialog from "..";
import { goToEditorStep } from "./goToEditorStep";

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
  window.localStorage.clear();
});

describe("EditRuleDialog phase 3 (right-column preview)", () => {
  it("pins the NICE quote while Guided is still building on step 1", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    expect(screen.getByTestId("highlight-wizard")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: /nice guideline wording for this rule/i }),
    ).toBeInTheDocument();
  });

  it("shows the live preview pane with the rule summary on dialog step 2", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    goToEditorStep(2);
    expect(
      screen.getByRole("region", { name: /nice guideline wording for this rule/i }),
    ).toBeInTheDocument();
    const pane = screen.getByRole("region", {
      name: /live preview of this rule/i,
    });
    expect(pane).toBeInTheDocument();
    expect(within(pane).getByText(/40 years or older/i)).toBeInTheDocument();
    expect(within(pane).getByText(/symptoms of lung cancer/i)).toBeInTheDocument();
  });

  it("Live preview pane shows 'What the system will do' alongside the summary", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={VAGUE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );
    goToEditorStep(2);
    expect(
      screen.getByRole("region", { name: /nice guideline wording for this rule/i }),
    ).toBeInTheDocument();
    const pane = screen.getByRole("region", {
      name: /live preview of this rule/i,
    });
    expect(
      within(pane).getByRole("region", {
        name: /what the system will do when this rule matches/i,
      }),
    ).toBeInTheDocument();
  });
});

describe.skip("Concept Coach (pending Guided port -- was Advanced ConceptPill only)", () => {
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
});
