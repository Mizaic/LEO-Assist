/**
 * VT-1A732988 -- problem list groups must reveal every remaining chip.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-7DE8E8ED
 *
 * Covers:
 *   TC-009: +n more is a control, not a dead label.
 *   TC-010: selecting +n more shows every remaining chip in that group.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProblemListView } from "@/components/patients/ProblemListView";
import type { CodedEntityRow } from "@/lib/patientEprApi";

jest.mock("@/components/patients/CodedEntityChip", () => ({
  CodedEntityChip: ({ name }: { name: string }) => (
    <span data-testid="coded-chip">{name}</span>
  ),
}));

function labEntity(index: number): CodedEntityRow {
  return {
    entity_type: "observable",
    name: `Lab result ${index}`,
    concept_id: `concept-${index}`,
  };
}

describe("VT-1A732988 - ProblemListView expand remaining chips", () => {
  test("TC-009: +n more is a control the clinician can select", () => {
    const entities = Array.from({ length: 18 }, (_, i) => labEntity(i + 1));
    render(
      <ProblemListView
        patientId="pat-1"
        entities={entities}
        maxPerGroup={8}
      />,
    );

    expect(screen.getByRole("button", { name: /10 more/i })).toBeInTheDocument();
    expect(screen.getByText("Lab result 8")).toBeInTheDocument();
    expect(screen.queryByText("Lab result 9")).not.toBeInTheDocument();
    expect(screen.queryByText("Lab result 18")).not.toBeInTheDocument();
  });

  test("TC-010: selecting +n more shows every remaining chip in the group", async () => {
    const user = userEvent.setup();
    const entities = Array.from({ length: 18 }, (_, i) => labEntity(i + 1));
    render(
      <ProblemListView
        patientId="pat-1"
        entities={entities}
        maxPerGroup={8}
      />,
    );

    await user.click(screen.getByRole("button", { name: /10 more/i }));

    expect(screen.getByText("Lab result 9")).toBeInTheDocument();
    expect(screen.getByText("Lab result 18")).toBeInTheDocument();
    expect(screen.getAllByTestId("coded-chip")).toHaveLength(18);
  });
});
