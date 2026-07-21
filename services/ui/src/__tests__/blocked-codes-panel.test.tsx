/**
 * BlockedCodesPanel component tests (UN-LEO-AI-093 / DI-LEO-AI-511).
 *
 * A blocked SNOMED code is stored as a bare id with no cached term. This
 * panel resolves each id's preferred term via the exact-id-match branch
 * of /api/terminology/search so a reviewer sees "Cigarette smoker"
 * instead of "code 230063004" when auditing a rule's exclusions.
 *
 * Asserted behaviour:
 *   - With no exclusions, shows the "Nothing blocked yet" empty state
 *     and does not call the search endpoint.
 *   - With exclusions, calls /api/terminology/search?q={id} for each id
 *     and renders the resolved friendly term as the chip label, with
 *     the raw code kept in a tooltip.
 *   - An id the search endpoint cannot resolve falls back to the
 *     "code {id}" label.
 *   - Clicking a chip's delete icon emits remove_excluded.
 *   - Clicking "Search a code to block" calls onRequestSearch.
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import BlockedCodesPanel from "@/app/admin/guidance/EditRuleDialog/BlockedCodesPanel";
import type { NodeUpdate } from "@/app/admin/guidance/EditRuleDialog/types";

function mockSearch(byId: Record<string, unknown[]>) {
  return jest.spyOn(global, "fetch").mockImplementation((url) => {
    const u = String(url);
    const match = u.match(/\/api\/terminology\/search\?q=([^&]+)/);
    const id = match ? decodeURIComponent(match[1]) : "";
    const rows = byId[id] ?? [];
    return Promise.resolve({
      ok: true,
      json: async () => rows,
      text: async () => JSON.stringify(rows),
    } as Response);
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("BlockedCodesPanel", () => {
  it("shows the empty state and does not call search when nothing is blocked", () => {
    const fetchSpy = mockSearch({});
    render(
      <BlockedCodesPanel
        nodeId="n1"
        excluded={[]}
        onUpdate={() => {}}
        onRequestSearch={() => {}}
      />,
    );
    expect(screen.getByText(/nothing blocked yet/i)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("resolves and shows the friendly term for a blocked id", async () => {
    const fetchSpy = mockSearch({
      "230063004": [
        {
          snomed_concept_id: "230063004",
          term: "Cigarette smoker (finding)",
          semantic_tag: "finding",
        },
      ],
    });
    render(
      <BlockedCodesPanel
        nodeId="n1"
        excluded={["230063004"]}
        onUpdate={() => {}}
        onRequestSearch={() => {}}
      />,
    );

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    expect(String(fetchSpy.mock.calls[0][0])).toMatch(
      /\/api\/terminology\/search\?q=230063004/,
    );
    expect(await screen.findByText(/cigarette smoker/i)).toBeInTheDocument();
    expect(screen.queryByText(/code 230063004/i)).not.toBeInTheDocument();
  });

  it("falls back to the raw code label when the id cannot be resolved", async () => {
    const fetchSpy = mockSearch({});
    render(
      <BlockedCodesPanel
        nodeId="n1"
        excluded={["999999999"]}
        onUpdate={() => {}}
        onRequestSearch={() => {}}
      />,
    );
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/code 999999999/i)).toBeInTheDocument();
  });

  it("emits remove_excluded when a resolved chip's delete icon is clicked", async () => {
    mockSearch({
      "230063004": [
        { snomed_concept_id: "230063004", term: "Cigarette smoker (finding)" },
      ],
    });
    const onUpdate = jest.fn<void, [NodeUpdate]>();
    render(
      <BlockedCodesPanel
        nodeId="n1"
        excluded={["230063004"]}
        onUpdate={onUpdate}
        onRequestSearch={() => {}}
      />,
    );
    const chip = await screen.findByText(/cigarette smoker/i);
    const deleteIcon = chip.parentElement?.querySelector(
      "svg[data-testid='CloseIcon']",
    );
    expect(deleteIcon).toBeTruthy();
    fireEvent.click(deleteIcon as Element);
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "remove_excluded",
      nodeId: "n1",
      conceptId: "230063004",
    });
  });

  it("calls onRequestSearch when 'Search a code to block' is clicked", () => {
    mockSearch({});
    const onRequestSearch = jest.fn();
    render(
      <BlockedCodesPanel
        nodeId="n1"
        excluded={[]}
        onUpdate={() => {}}
        onRequestSearch={onRequestSearch}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /search a code to block/i }),
    );
    expect(onRequestSearch).toHaveBeenCalledTimes(1);
  });

  it("blocks a manually pasted numeric SNOMED id", () => {
    mockSearch({});
    const onUpdate = jest.fn<void, [NodeUpdate]>();
    render(
      <BlockedCodesPanel
        nodeId="n1"
        excluded={[]}
        onUpdate={onUpdate}
        onRequestSearch={() => {}}
      />,
    );
    fireEvent.change(
      screen.getByLabelText(/block a snomed code by id/i),
      { target: { value: "123456" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /^block$/i }));
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "add_excluded",
      nodeId: "n1",
      conceptId: "123456",
    });
  });
});
