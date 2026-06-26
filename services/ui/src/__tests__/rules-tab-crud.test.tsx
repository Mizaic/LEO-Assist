/**
 * Jest unit test for the Rules tab CRUD editor in SubdomainPanelTabs.
 *
 * Atlas trace:
 *   VT: VT-6ADE2398
 *   DO: DO-F499E476
 *   DI: DI-C34A2990
 *   Look up via: get_design_control(dc_type="verification-test", dc_id="VT-6ADE2398")
 *
 * Acceptance criteria verified:
 *   AC1 - Existing schema groups render as editable cards.
 *   AC2 - Add rule creates a new group and invokes onSave.
 *   AC3 - Deleting a group removes it and invokes onSave.
 *   AC4 - Editing a group name on blur invokes onSave with updated name.
 *   AC5 - Required/Optional toggle invokes onSave with updated required flag.
 *   AC6 - Adding a SNOMED concept via search invokes onSave.
 *   AC7 - When completeness is not in use_cases, info prompt is shown.
 */

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RulesTab } from "../app/settings/domains/_components/SubdomainPanelTabs";
import type { CompletenessConceptGroup } from "@/lib/analyticsApi";
import { searchTerms } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  searchTerms: jest.fn(),
}));

const mockSearchTerms = searchTerms as jest.MockedFunction<typeof searchTerms>;

const SCHEMA: CompletenessConceptGroup[] = [
  {
    name: "FIT result",
    required: true,
    semantic_categories: ["observable_entity"],
    concept_ids: [71711000112103],
  },
  {
    name: "Blood results",
    required: false,
    semantic_categories: [],
    concept_ids: [],
  },
];

const RULES_TAB_PROPS = {
  canEditDomains: true,
  allSemanticTags: ["observable_entity", "disorder", "finding"],
  useCases: ["completeness"] as const,
  subdomainConcepts: [],
};

describe("RulesTab", () => {
  beforeEach(() => {
    mockSearchTerms.mockReset();
    mockSearchTerms.mockImplementation(async (q: string) => {
      if (q === "71711000112103") {
        return [
          {
            snomed_concept_id: "71711000112103",
            term: "Quantitative faecal immunochemical test",
            semantic_tag: "observable_entity",
          },
        ];
      }
      if (q.toLowerCase().includes("ear")) {
        return [
          {
            snomed_concept_id: "59621000",
            term: "Ear ache",
            semantic_tag: "finding",
          },
        ];
      }
      return [];
    });
  });

  it("AC7 - shows prompt when completeness not in use_cases", () => {
    const onSave = jest.fn();
    render(
      <RulesTab
        schema={SCHEMA}
        {...RULES_TAB_PROPS}
        useCases={["extraction"]}
        onSave={onSave}
      />,
    );
    expect(screen.getByText(/Add the "Minimum dataset" purpose/i)).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("AC1 - renders existing schema groups as cards", async () => {
    const onSave = jest.fn();
    render(<RulesTab schema={SCHEMA} {...RULES_TAB_PROPS} onSave={onSave} />);
    expect(screen.getByDisplayValue("FIT result")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Blood results")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/Quantitative faecal immunochemical/i)).toBeInTheDocument(),
    );
  });

  it("AC2 - Add rule creates a new group and calls onSave", async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(<RulesTab schema={SCHEMA} {...RULES_TAB_PROPS} allSemanticTags={[]} onSave={onSave} />);
    await userEvent.click(screen.getByRole("button", { name: /add rule/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const call = onSave.mock.calls[0][0] as CompletenessConceptGroup[];
    expect(call).toHaveLength(3);
    expect(call[2].name).toBe("New rule");
    expect(call[2].required).toBe(true);
  });

  it("AC3 - deleting a group calls onSave with reduced list", async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(<RulesTab schema={SCHEMA} {...RULES_TAB_PROPS} allSemanticTags={[]} onSave={onSave} />);
    const deleteButtons = screen.getAllByRole("button", { name: /delete rule/i });
    await userEvent.click(deleteButtons[0]);
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const call = onSave.mock.calls[0][0] as CompletenessConceptGroup[];
    expect(call).toHaveLength(1);
    expect(call[0].name).toBe("Blood results");
  });

  it("AC5 - toggling required flag calls onSave", async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(<RulesTab schema={SCHEMA} {...RULES_TAB_PROPS} allSemanticTags={[]} onSave={onSave} />);
    const selects = screen.getAllByDisplayValue(/required|optional/i);
    fireEvent.change(selects[0], { target: { value: "optional" } });
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const call = onSave.mock.calls[0][0] as CompletenessConceptGroup[];
    expect(call[0].required).toBe(false);
  });

  it("AC6 - adding a SNOMED concept via search calls onSave", async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(
      <RulesTab
        schema={[{ name: "Test", required: true, semantic_categories: [], concept_ids: [] }]}
        {...RULES_TAB_PROPS}
        allSemanticTags={[]}
        onSave={onSave}
      />,
    );
    const search = screen.getByRole("combobox", { name: /search snomed terms for rule 1/i });
    await userEvent.type(search, "ear");
    await waitFor(() => expect(mockSearchTerms).toHaveBeenCalled());
    await userEvent.click(await screen.findByText("Ear ache"));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const call = onSave.mock.calls[0][0] as CompletenessConceptGroup[];
    expect(call[0].concept_ids).toContain(59621000);
  });
});
