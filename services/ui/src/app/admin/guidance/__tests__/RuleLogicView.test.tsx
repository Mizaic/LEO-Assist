/**
 * VT-94C886CA -- Read-only rule logic renderer.
 *
 * Live-render verification:
 *   - A multi-pathway rule (top-level OR with 2+ branches) renders as
 *     PATHWAY A / B / C cards under a "matches any one of these pathways"
 *     heading, mirroring the editor's pattern.
 *   - A single-pathway rule renders the plain "ALL of these" / "ANY of
 *     these" tree (no pathway cards).
 *   - The legacy v1 fallback (no logic_tree) still renders present /
 *     absent chips.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { RuleDetailPanel, isPathwaySplit, type LogicTreeNode } from "../RuleLogicView";

function concept(term: string, snomed = "100000000"): LogicTreeNode {
  return {
    kind: "CONCEPT",
    criterion: {
      term,
      snomed_concept_id: snomed,
      preferred_term: term,
      semantic_tag: "finding",
    },
  };
}

function multiSeedConcept(terms: string[]): LogicTreeNode {
  return {
    kind: "CONCEPT",
    criterion: {
      term: terms[0],
      snomed_concept_id: "1",
      preferred_term: terms[0],
      primary_concept_id: "1",
      seeds: terms.map((term, i) => ({
        snomed_concept_id: String(i + 1),
        preferred_term: term,
      })),
    },
  };
}

const NG12_LIKE_TREE: LogicTreeNode = {
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
      kind: "OR",
      children: [
        {
          kind: "AT_LEAST",
          min: 2,
          children: [
            concept("Cough", "49727002"),
            concept("Fatigue", "84229001"),
            concept("Dyspnea", "267036007"),
          ],
        },
        {
          kind: "AND",
          children: [
            concept("Smoker", "77176002"),
            {
              kind: "AT_LEAST",
              min: 1,
              children: [concept("Cough", "49727002")],
            },
          ],
        },
        {
          kind: "AND",
          children: [
            concept("History of asbestos exposure", "428270001"),
            {
              kind: "AT_LEAST",
              min: 1,
              children: [concept("Cough", "49727002")],
            },
          ],
        },
      ],
    },
  ],
};

const SINGLE_PATHWAY_TREE: LogicTreeNode = {
  kind: "AND",
  children: [
    {
      kind: "AT_LEAST",
      min: 1,
      children: [concept("Rectal bleeding", "443416000")],
    },
  ],
};

/** NG12 1.1.3 shape: age + flat OR of findings = one situation, not N pathways. */
const NG113_FLAT_OR_TREE: LogicTreeNode = {
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
      kind: "OR",
      children: [
        concept("Lower respiratory tract infection", "50417007"),
        concept("Finger clubbing", "30760008"),
        concept("Supraclavicular lymphadenopathy", "127088000"),
        concept("Cervical lymphadenopathy", "127086001"),
        concept("Thrombocytosis", "6631009"),
      ],
    },
  ],
};

function renderTree(
  tree: LogicTreeNode | null,
  action?: {
    snomed_concept_id: string | null;
    preferred_term: string;
    semantic_tag?: string;
    term?: string;
  },
) {
  return render(
    <RuleDetailPanel
      rule={{
        strength: "refer",
        action,
        logic_tree: tree,
        present_criteria: [],
        absent_criteria: [],
      }}
    />,
  );
}

describe("isPathwaySplit", () => {
  it("returns true for an OR of grouped branches at depth 0", () => {
    expect(
      isPathwaySplit(
        {
          kind: "OR",
          children: [
            { kind: "AND", children: [concept("a")] },
            { kind: "AND", children: [concept("b")] },
          ],
        },
        0,
      ),
    ).toBe(true);
  });

  it("returns false for a flat OR of leaf concepts (one situation)", () => {
    expect(
      isPathwaySplit(
        { kind: "OR", children: [concept("a"), concept("b")] },
        0,
      ),
    ).toBe(false);
  });

  it("returns false for an OR deeper than depth 1", () => {
    expect(
      isPathwaySplit(
        {
          kind: "OR",
          children: [
            { kind: "AND", children: [concept("a")] },
            { kind: "AND", children: [concept("b")] },
          ],
        },
        2,
      ),
    ).toBe(false);
  });

  it("returns false for a single-child OR", () => {
    expect(isPathwaySplit({ kind: "OR", children: [concept("a")] }, 0)).toBe(
      false,
    );
  });

  it("returns false for a non-OR group", () => {
    expect(
      isPathwaySplit(
        { kind: "AND", children: [concept("a"), concept("b")] },
        0,
      ),
    ).toBe(false);
  });
});

describe("RuleDetailPanel - multi-pathway tree (NG12-like)", () => {
  it("renders the plain-English pathway heading", () => {
    renderTree(NG12_LIKE_TREE);
    expect(
      screen.getByText(
        /The rule fires if the patient matches any one of these pathways:/i,
      ),
    ).toBeInTheDocument();
  });

  it("labels each branch as PATHWAY A / B / C", () => {
    renderTree(NG12_LIKE_TREE);
    expect(screen.getByText(/^Pathway A$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Pathway B$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Pathway C$/i)).toBeInTheDocument();
  });

  it("does not relabel the OR branch as a generic 'ANY of these' header", () => {
    // Without the pathway-cards layer the same tree would show a top-level
    // "ANY of these" caption above the three branches; the new layout
    // replaces that with the plain-English pathway heading.
    renderTree(NG12_LIKE_TREE);
    expect(screen.queryByText(/^ANY of these$/i)).not.toBeInTheDocument();
  });

  it("still renders the demographic chip alongside the pathway cards", () => {
    renderTree(NG12_LIKE_TREE);
    expect(screen.getByText(/age is at least 40 years/i)).toBeInTheDocument();
  });

  it("uses a group landmark with the 'Patient pathways' label", () => {
    renderTree(NG12_LIKE_TREE);
    expect(
      screen.getByRole("group", { name: /patient pathways/i }),
    ).toBeInTheDocument();
  });

  it("renders the soft-cased 'Any 2 or more of these (of 3)' pill for the symptom-cluster pathway (Pathway A)", () => {
    // Mirrors the editor's InlineAtLeastView: the AT_LEAST group whose
    // children are all SNOMED concepts shows the count out of total
    // ("X of N OF THESE") so the reviewer can see at a glance that the
    // rule fires when any 2 of the listed symptoms are present.
    renderTree(NG12_LIKE_TREE);
    expect(screen.getByText(/^Any 2 or more of these \(of 3\)$/i)).toBeInTheDocument();
  });

  it("renders the OR connector badges between adjacent pathway cards", () => {
    renderTree(NG12_LIKE_TREE);
    // 3 pathways -> 2 OR connectors between them.
    expect(screen.getAllByRole("img", { name: /^or$/i })).toHaveLength(2);
  });
});

describe("RuleDetailPanel - named pathways (Phase 2)", () => {
  // A multi-pathway rule whose group children carry plain-English
  // ``name`` fields renders the names verbatim as the card titles.
  // Unnamed branches keep the positional letter so legacy guidelines
  // still render. Atlas trace: DI-2E01CC45 / DO-E67AFBE2.
  const NAMED_PATHWAY_TREE: LogicTreeNode = {
    kind: "OR",
    children: [
      {
        kind: "AND",
        name: "Possible cancer",
        children: [concept("Cough", "49727002")],
      },
      {
        kind: "AND",
        children: [concept("Fatigue", "84229001")],
      },
      {
        kind: "AND",
        name: "Symptom watch",
        children: [concept("Dyspnea", "267036007")],
      },
    ],
  };

  it("uses each group's name as the pathway card title when set", () => {
    renderTree(NAMED_PATHWAY_TREE);
    expect(screen.getByText("Possible cancer")).toBeInTheDocument();
    expect(screen.getByText("Symptom watch")).toBeInTheDocument();
  });

  it("falls back to the positional letter when a name is missing", () => {
    renderTree(NAMED_PATHWAY_TREE);
    expect(screen.getByText(/^Pathway B$/)).toBeInTheDocument();
    expect(screen.queryByText(/^Pathway A$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Pathway C$/)).not.toBeInTheDocument();
  });
});

describe("RuleDetailPanel - single-pathway tree", () => {
  it("does not render a pathway heading", () => {
    renderTree(SINGLE_PATHWAY_TREE);
    expect(
      screen.queryByText(
        /The rule fires if the patient matches any one of these pathways:/i,
      ),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/^Pathway A$/i)).not.toBeInTheDocument();
  });

  it("renders the soft-cased 'Any 1 or more of these (of 1)' pill for the single-symptom branch", () => {
    renderTree(SINGLE_PATHWAY_TREE);
    expect(
      screen.getByText(/^Any 1 or more of these \(of 1\)$/i),
    ).toBeInTheDocument();
  });

  it("NG12 1.1.3: flat OR of findings under age is one situation, not Pathway A-E", () => {
    renderTree(NG113_FLAT_OR_TREE);
    expect(
      screen.queryByText(
        /The rule fires if the patient matches any one of these pathways:/i,
      ),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/^Pathway A$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Pathway E$/i)).not.toBeInTheDocument();
    expect(screen.getByText(/age is at least 40 years/i)).toBeInTheDocument();
    expect(screen.getByText(/Finger clubbing/i)).toBeInTheDocument();
    // Flat OR of leaves renders as the ordinary "ANY of these" group.
    expect(screen.getByText(/^ANY of these$/i)).toBeInTheDocument();
  });
});

describe("RuleDetailPanel - recommended action", () => {
  it("shows the selected procedure next to the recommendation strength", () => {
    renderTree(SINGLE_PATHWAY_TREE, {
      snomed_concept_id: "168731009",
      preferred_term: "Plain X-ray of chest (procedure)",
      semantic_tag: "procedure",
    });

    expect(
      screen.getByText(/Refer urgently: Plain X-ray of chest/i),
    ).toBeInTheDocument();
  });

  it("shows clinical priority and due-within on the card action block", () => {
    render(
      <RuleDetailPanel
        rule={{
          strength: "consider",
          action_priority: "urgent",
          action_due_days: 14,
          actions: [
            {
              criterion: {
                snomed_concept_id: "53059001",
                preferred_term: "Esophagogastroduodenoscopy",
              },
              strength: "consider",
            },
          ],
          logic_tree: SINGLE_PATHWAY_TREE,
          present_criteria: [],
          absent_criteria: [],
        }}
      />,
    );
    expect(
      screen.getByLabelText(/clinical priority: urgent, within 14 days/i),
    ).toBeInTheDocument();
  });

  it("shows Routine without a due-within clause", () => {
    render(
      <RuleDetailPanel
        rule={{
          strength: "consider",
          action_priority: "routine",
          action_due_days: null,
          actions: [
            {
              criterion: {
                snomed_concept_id: "53059001",
                preferred_term: "Esophagogastroduodenoscopy",
              },
              strength: "consider",
            },
          ],
          logic_tree: SINGLE_PATHWAY_TREE,
          present_criteria: [],
          absent_criteria: [],
        }}
      />,
    );
    expect(screen.getByLabelText(/^clinical priority: routine$/i)).toBeInTheDocument();
  });
});

describe("RuleDetailPanel - multi-seed CONCEPT chip tooltip", () => {
  // Regression: a chip built from several synonym seeds ("Add another
  // code that means the same") only showed its headline term and own
  // SNOMED code in the tooltip, hiding every other finding the chip
  // actually covers. The tooltip must list the other seeds' plain
  // English terms, not bare SNOMED ids.
  it("lists the other seeds' preferred terms in the tooltip, not their codes", async () => {
    const user = userEvent.setup();
    const tree: LogicTreeNode = {
      kind: "AND",
      children: [
        {
          kind: "AT_LEAST",
          min: 1,
          children: [
            multiSeedConcept([
              "Abnormal blood test",
              "Hemoglobin below reference range",
              "Raised ESR",
            ]),
          ],
        },
      ],
    };
    renderTree(tree);

    await user.hover(screen.getByText("Abnormal blood test"));
    const tip = await screen.findByRole("tooltip");

    expect(tip).toHaveTextContent(/abnormal blood test \(snomed 1\)/i);
    expect(tip).toHaveTextContent(/also matches/i);
    expect(tip).toHaveTextContent(/hemoglobin below reference range/i);
    expect(tip).toHaveTextContent(/raised esr/i);
    expect(tip).not.toHaveTextContent(/snomed 2/i);
    expect(tip).not.toHaveTextContent(/snomed 3/i);
  });

  it("shows just the headline term and code for a single-seed chip, with no 'Also matches'", async () => {
    const user = userEvent.setup();
    renderTree(SINGLE_PATHWAY_TREE);

    await user.hover(screen.getByText("Rectal bleeding"));
    const tip = await screen.findByRole("tooltip");

    expect(tip).toHaveTextContent(/rectal bleeding \(snomed 443416000\)/i);
    expect(tip).not.toHaveTextContent(/also matches/i);
  });
});

describe("RuleDetailPanel - v1 schema fallback (no logic_tree)", () => {
  it("renders ANY-of-these chips for present criteria", () => {
    render(
      <RuleDetailPanel
        rule={{
          strength: "refer",
          logic_tree: null,
          present_criteria: [
            {
              predicate: "PRESENT",
              concept_id: "443416000",
              preferred_term: "Rectal bleeding",
            },
          ],
          absent_criteria: [],
        }}
      />,
    );
    expect(screen.getByText(/^ANY of these$/i)).toBeInTheDocument();
    expect(screen.getByText(/Rectal bleeding/i)).toBeInTheDocument();
  });

  it("renders empty-state copy when there are no criteria at all", () => {
    render(
      <RuleDetailPanel
        rule={{
          strength: "refer",
          logic_tree: null,
          present_criteria: [],
          absent_criteria: [],
        }}
      />,
    );
    expect(
      screen.getByText(/No criteria stored for this rule\./i),
    ).toBeInTheDocument();
  });
});
