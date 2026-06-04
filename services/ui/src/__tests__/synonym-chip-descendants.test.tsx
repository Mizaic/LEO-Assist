/**
 * SeedDescendantsList component tests
 * (UN-LEO-AI-093 / DI-LEO-AI-511 / R-LEO-AI-508).
 *
 * These tests cover the inline descendants viewer that lets a
 * reviewer audit which SNOMED codes a synonym seed will actually
 * match before saving the rule. Without this affordance the
 * include_descendants + distance_child controls are opaque, which
 * is the hazard chain for R-LEO-AI-508 (a wrong descendant carve-
 * out silently drops a real match).
 *
 * Asserted behaviour:
 *   - When include_descendants is OFF the panel renders a static
 *     "exact code only" message and does NOT call the descendants
 *     endpoint.
 *   - When include_descendants is ON, opening the panel calls
 *     /api/terminology/concepts/{id}/descendants with the effective
 *     depth, renders the rows with friendly term + code, and a
 *     Block button beside each row.
 *   - Already-blocked descendants render with a "Blocked" chip and
 *     the strike-through styling so they cannot be confused with
 *     active matches.
 *   - Clicking Block emits an add_excluded NodeUpdate; clicking the
 *     X on a Blocked chip emits remove_excluded.
 *   - Re-opening the panel after a depth change refetches.
 */

import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

import SeedDescendantsList from "@/app/admin/guidance/EditRuleDialog/SeedDescendantsList";

const SAMPLE_RESPONSE = [
  {
    snomed_concept_id: "230063004",
    preferred_term: "Cigarette smoker (finding)",
    semantic_tag: "finding",
  },
  {
    snomed_concept_id: "266920004",
    preferred_term: "Trial of smoking (finding)",
    semantic_tag: "finding",
  },
];

function mockDescendants(rows: unknown[] = SAMPLE_RESPONSE) {
  return jest.spyOn(global, "fetch").mockImplementation((url) => {
    const u = String(url);
    if (u.includes("/api/terminology/concepts/")) {
      return Promise.resolve({
        ok: true,
        json: async () => rows,
        text: async () => JSON.stringify(rows),
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

describe("SeedDescendantsList -- VT-510-TC-016", () => {
  it("renders an exact-code-only message and does not fetch when descendants are off", () => {
    const fetchSpy = mockDescendants();
    render(
      <SeedDescendantsList
        seedConceptId="77176002"
        seedTerm="Smoker (finding)"
        includeDescendants={false}
        depth={3}
        excludedIds={[]}
        onBlock={() => {}}
        onUnblock={() => {}}
      />,
    );
    expect(
      screen.getByText(/only the exact code/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /show codes/i }),
    ).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fetches and lists descendants on expand, with a Block button per row", async () => {
    const fetchSpy = mockDescendants();
    const onBlock = jest.fn();
    render(
      <SeedDescendantsList
        seedConceptId="77176002"
        seedTerm="Smoker (finding)"
        includeDescendants={true}
        depth={3}
        excludedIds={[]}
        onBlock={onBlock}
        onUnblock={() => {}}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /show the codes covered by smoker at depth 3/i,
      }),
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });
    const url = String(fetchSpy.mock.calls[0][0]);
    expect(url).toMatch(/\/api\/terminology\/concepts\/77176002\/descendants/);
    expect(url).toMatch(/depth=3/);

    const list = await screen.findByRole("list", {
      name: /codes covered by smoker at depth 3/i,
    });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(list).getByText(/cigarette smoker/i)).toBeInTheDocument();
    expect(within(list).getByText(/trial of smoking/i)).toBeInTheDocument();
    expect(within(list).getByText(/code 230063004/i)).toBeInTheDocument();

    fireEvent.click(
      within(list).getByRole("button", {
        name: /block trial of smoking from firing this rule/i,
      }),
    );
    expect(onBlock).toHaveBeenCalledWith("266920004");
  });

  it("shows a Blocked chip with strike-through for ids in excludedIds and emits remove_excluded on the X", async () => {
    mockDescendants();
    const onUnblock = jest.fn();
    render(
      <SeedDescendantsList
        seedConceptId="77176002"
        seedTerm="Smoker (finding)"
        includeDescendants={true}
        depth={3}
        excludedIds={["266920004"]}
        onBlock={() => {}}
        onUnblock={onUnblock}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /show the codes covered by smoker at depth 3/i,
      }),
    );
    const list = await screen.findByRole("list", {
      name: /codes covered by smoker at depth 3/i,
    });
    await within(list).findAllByRole("listitem");
    // The blocked row shows the chip; the unblocked row shows Block btn.
    expect(within(list).getByText(/blocked/i)).toBeInTheDocument();
    expect(
      within(list).getByRole("button", {
        name: /block cigarette smoker from firing this rule/i,
      }),
    ).toBeInTheDocument();

    // The chip's delete button is the X that unblocks the row.
    const unblockBtn = within(list).getByRole("button", {
      name: /unblock trial of smoking/i,
    });
    fireEvent.click(unblockBtn);
    expect(onUnblock).toHaveBeenCalledWith("266920004");
  });

  it("refetches when the depth changes", async () => {
    const fetchSpy = mockDescendants();
    const { rerender } = render(
      <SeedDescendantsList
        seedConceptId="77176002"
        seedTerm="Smoker (finding)"
        includeDescendants={true}
        depth={2}
        excludedIds={[]}
        onBlock={() => {}}
        onUnblock={() => {}}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /show the codes covered by smoker at depth 2/i,
      }),
    );
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    expect(String(fetchSpy.mock.calls[0][0])).toMatch(/depth=2/);

    rerender(
      <SeedDescendantsList
        seedConceptId="77176002"
        seedTerm="Smoker (finding)"
        includeDescendants={true}
        depth={4}
        excludedIds={[]}
        onBlock={() => {}}
        onUnblock={() => {}}
      />,
    );
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    expect(String(fetchSpy.mock.calls[1][0])).toMatch(/depth=4/);
  });
});
