/**
 * VT-LEO-AI-511 -- TC-006 (actions omitted when no procedure chip
 * touched), TC-007 (actions populated when a procedure chip touched),
 * TC-008 (node_ids stripped from logic_tree).
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import EditRuleDialog from "../app/admin/guidance/EditRuleDialog";

const SAMPLE_RULE = {
  rule_id: "rule:NG12:abc",
  name: "Mesothelioma urgent X-ray",
  strength: "offer",
  guideline_id: "NG12",
  chapter_title: "Recommendations organised by site of cancer",
  recommendation_text: "Offer urgent chest X-ray.",
  logic_tree: {
    kind: "AND",
    children: [
      {
        kind: "CONCEPT",
        criterion: {
          snomed_concept_id: "49727002",
          preferred_term: "Cough (finding)",
          semantic_tag: "finding",
        },
      },
    ],
  },
  actions: [
    {
      criterion: {
        snomed_concept_id: "168731009",
        preferred_term: "Plain chest X-ray (procedure)",
        semantic_tag: "procedure",
      },
      strength: "offer",
    },
  ],
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

function goToStep(n: 1 | 2 | 3) {
  fireEvent.click(
    screen.getAllByRole("button", { name: new RegExp(`^Step ${n} of 3`, "i") })[0],
  );
}

function fillReason(text: string) {
  goToStep(3);
  fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
    target: { value: text },
  });
}

function walkTree(
  node: Record<string, unknown>,
  visit: (n: Record<string, unknown>) => void,
) {
  visit(node);
  const children = node.children as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(children)) {
    for (const child of children) walkTree(child, visit);
  }
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("EditRuleDialog save payload -- VT-511-TC-006/007/008", () => {
  it("omits actions from the payload when no procedure chip was ever touched", async () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={onSave}
      />,
    );
    fillReason("Tightened criteria only");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const payload = onSave.mock.calls[0][0];
    expect(payload.actions).toBeUndefined();
    expect(payload.reason).toBe("Tightened criteria only");
    expect(payload.logic_tree.kind).toBe("AND");
  });

  it("includes the touched procedure's criterion in the actions payload", async () => {
    mockSearch([
      {
        snomed_concept_id: "16310003",
        term: "Diagnostic ultrasound (procedure)",
        semantic_tag: "procedure",
      },
    ]);
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={onSave}
      />,
    );

    goToStep(2);
    fireEvent.click(
      screen.getByRole("button", {
        name: /plain chest x-ray\. click to pick a different procedure\./i,
      }),
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Use Diagnostic ultrasound$/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole("button", { name: /^Use Diagnostic ultrasound$/i }),
    );

    fillReason("Switched to ultrasound");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const payload = onSave.mock.calls[0][0];
    expect(payload.actions).toBeDefined();
    expect(payload.actions).toHaveLength(1);
    expect(payload.actions[0].criterion.snomed_concept_id).toBe("16310003");
  });

  it("strips node_id fields from logic_tree in the save payload", async () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={onSave}
      />,
    );
    fillReason("Reviewed only");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const payload = onSave.mock.calls[0][0];
    walkTree(payload.logic_tree, (n) => {
      expect("node_id" in n).toBe(false);
    });
  });
});
