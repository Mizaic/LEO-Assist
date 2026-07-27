/**
 * Trigger wiring for "Ask LEO for ideas":
 * - ConceptSearchPanel no-results state
 * - ConceptCoachPopover empty-suggestions branch
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ConceptCoachPopover from "../ConceptCoachPopover";
import ConceptSearchPanel from "../ConceptSearchPanel";

function mockEmptySearch() {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    const href = String(url);
    if (href.includes("/api/guidance/concepts/expand-topic")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ terms: ["cough"], reason: "ok" }),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => [] } as Response);
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Ask LEO triggers", () => {
  it("shows Ask LEO on ConceptSearchPanel no-results when onAddMany is provided", async () => {
    const user = userEvent.setup();
    mockEmptySearch();
    render(
      <ConceptSearchPanel
        mode="add"
        focusLabel={null}
        initialQuery="skin changes suggestive of breast cancer"
        onPick={jest.fn()}
        onAddMany={jest.fn()}
      />,
    );

    expect(
      await screen.findByText(/No clinical terms match/i),
    ).toBeInTheDocument();
    const ask = screen.getByRole("button", { name: /Ask LEO for ideas/i });
    await user.click(ask);
    expect(
      await screen.findByRole("dialog", { name: /Ask LEO for ideas/i }),
    ).toBeInTheDocument();
  });

  it("hides Ask LEO on ConceptSearchPanel when onAddMany is omitted", async () => {
    mockEmptySearch();
    render(
      <ConceptSearchPanel
        mode="add"
        focusLabel={null}
        initialQuery="zzzznotaterm"
        onPick={jest.fn()}
      />,
    );
    await screen.findByText(/No clinical terms match/i);
    expect(
      screen.queryByRole("button", { name: /Ask LEO for ideas/i }),
    ).not.toBeInTheDocument();
  });

  it("shows Ask LEO on ConceptCoachPopover when there are no curated suggestions", async () => {
    const user = userEvent.setup();
    mockEmptySearch();
    const anchor = document.createElement("button");
    document.body.appendChild(anchor);
    render(
      <ConceptCoachPopover
        open
        anchorEl={anchor}
        vagueTerm="Markers of foobar syndrome"
        match={{
          isVague: true,
          topic: "foobar syndrome",
          patternLabel: "topic_of",
          reason: "This phrase does not list the specific findings.",
        }}
        onClose={jest.fn()}
        onAddCriteria={jest.fn()}
        onSearchMore={jest.fn()}
      />,
    );

    expect(screen.getByText(/ready-made list/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Ask LEO for ideas/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("dialog", { name: /Ask LEO for ideas/i }),
      ).toBeInTheDocument();
    });
  });
});
