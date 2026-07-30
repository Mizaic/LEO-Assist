/**
 * Live-render tests for GuidelineChangesDrawer's "possible move" gate --
 * nice-renumber-ambiguous-prompt.
 *
 * Atlas trace: DO-2C03CA0E / DI-3F771AFB
 *
 * Covers:
 *  - No possible_moves -> Confirm re-ingest is enabled immediately.
 *  - One possible_move, unanswered -> Confirm re-ingest is disabled.
 *  - Answering "Yes, it moved" (or "No, unrelated") enables Confirm re-ingest.
 *  - Multiple possible_moves all need an answer before the button enables.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GuidelineChangesDrawer from "../GuidelineChangesDrawer";

/** Waits for one possible-move card to render, keyed the same way the
 * component keys it ("removedNumber|addedNumber"). Query by test id
 * rather than sentence text since "Did X move to become Y?" splits
 * across <strong> nodes and text queries don't match across elements. */
async function findPossibleMoveCard(removedNumber: string, addedNumber: string) {
  return screen.findByTestId(
    `possible-move-${removedNumber}|${addedNumber}`,
    undefined,
    { timeout: 3000 }
  );
}

function jsonResponse(body: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
  } as Response);
}

function makeFetch(diff: Record<string, unknown>) {
  return jest.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes("/diff/start") && init?.method === "POST") {
      return jsonResponse({ job_id: "job-1" });
    }
    if (url.includes("/diff/job-1")) {
      return jsonResponse({ status: "done", diff });
    }
    return jsonResponse({});
  });
}

const BASE_DIFF = {
  added: [],
  removed: [],
  modified: [],
  unchanged_count: 5,
  total_stored: 5,
  total_remote: 6,
  _unchanged_numbers: [],
};

afterEach(() => {
  jest.restoreAllMocks();
});

describe("GuidelineChangesDrawer: possible-move confirmation gate", () => {
  it("enables Confirm re-ingest immediately when there are no possible moves", async () => {
    global.fetch = makeFetch({
      ...BASE_DIFF,
      added: [{ number: "1.5.1", text: "New rec.", section_title: "" }],
      possible_moves: [],
    });
    const onConfirmIngest = jest.fn();

    render(
      <GuidelineChangesDrawer
        code="NG12"
        onClose={jest.fn()}
        onConfirmIngest={onConfirmIngest}
      />
    );

    const confirmButton = await screen.findByRole(
      "button",
      { name: /confirm re-ingest/i },
      { timeout: 3000 }
    );
    expect(confirmButton).toBeEnabled();
  });

  it("disables Confirm re-ingest while a possible move is unanswered", async () => {
    global.fetch = makeFetch({
      ...BASE_DIFF,
      added: [{ number: "1.2.10", text: "Reworded rec.", section_title: "" }],
      removed: [
        {
          number: "1.2.9",
          text: "Original rec.",
          section_title: "",
          rules: [],
        },
      ],
      possible_moves: [
        { removed_number: "1.2.9", added_number: "1.2.10", score: 0.62 },
      ],
    });

    render(
      <GuidelineChangesDrawer
        code="NG12"
        onClose={jest.fn()}
        onConfirmIngest={jest.fn()}
      />
    );

    await findPossibleMoveCard("1.2.9", "1.2.10");
    const confirmButton = screen.getByRole("button", {
      name: /confirm re-ingest/i,
    });
    expect(confirmButton).toBeDisabled();
    expect(
      screen.getByText(/answer yes or no for every possible move/i)
    ).toBeInTheDocument();
  });

  it("enables Confirm re-ingest once the reviewer answers 'Yes, it moved'", async () => {
    const user = userEvent.setup();
    global.fetch = makeFetch({
      ...BASE_DIFF,
      added: [{ number: "1.2.10", text: "Reworded rec.", section_title: "" }],
      removed: [
        {
          number: "1.2.9",
          text: "Original rec.",
          section_title: "",
          rules: [],
        },
      ],
      possible_moves: [
        { removed_number: "1.2.9", added_number: "1.2.10", score: 0.62 },
      ],
    });

    render(
      <GuidelineChangesDrawer
        code="NG12"
        onClose={jest.fn()}
        onConfirmIngest={jest.fn()}
      />
    );

    await findPossibleMoveCard("1.2.9", "1.2.10");
    await user.click(screen.getByRole("button", { name: /yes, it moved/i }));

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /confirm re-ingest/i })
      ).toBeEnabled()
    );
  });

  it("enables Confirm re-ingest once the reviewer answers 'No, unrelated'", async () => {
    const user = userEvent.setup();
    global.fetch = makeFetch({
      ...BASE_DIFF,
      added: [{ number: "1.2.10", text: "Reworded rec.", section_title: "" }],
      removed: [
        {
          number: "1.2.9",
          text: "Original rec.",
          section_title: "",
          rules: [],
        },
      ],
      possible_moves: [
        { removed_number: "1.2.9", added_number: "1.2.10", score: 0.62 },
      ],
    });

    render(
      <GuidelineChangesDrawer
        code="NG12"
        onClose={jest.fn()}
        onConfirmIngest={jest.fn()}
      />
    );

    await findPossibleMoveCard("1.2.9", "1.2.10");
    await user.click(screen.getByRole("button", { name: /no, unrelated/i }));

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /confirm re-ingest/i })
      ).toBeEnabled()
    );
  });

  it("requires every possible move to be answered, not just the first", async () => {
    const user = userEvent.setup();
    global.fetch = makeFetch({
      ...BASE_DIFF,
      added: [
        { number: "1.3.9", text: "Rec A.", section_title: "" },
        { number: "1.4.9", text: "Rec B.", section_title: "" },
      ],
      removed: [
        { number: "1.3.1", text: "Old A.", section_title: "", rules: [] },
        { number: "1.4.1", text: "Old B.", section_title: "", rules: [] },
      ],
      possible_moves: [
        { removed_number: "1.3.1", added_number: "1.3.9", score: 0.6 },
        { removed_number: "1.4.1", added_number: "1.4.9", score: 0.58 },
      ],
    });

    render(
      <GuidelineChangesDrawer
        code="NG12"
        onClose={jest.fn()}
        onConfirmIngest={jest.fn()}
      />
    );

    const firstCard = await findPossibleMoveCard("1.3.1", "1.3.9");
    await findPossibleMoveCard("1.4.1", "1.4.9");
    const yesButtons = screen.getAllByRole("button", { name: /yes, it moved/i });
    expect(yesButtons).toHaveLength(2);
    expect(firstCard).toContainElement(yesButtons[0]);
    await user.click(yesButtons[0]);

    // Only the first of two moves answered -- still disabled.
    expect(
      screen.getByRole("button", { name: /confirm re-ingest/i })
    ).toBeDisabled();

    await user.click(yesButtons[1]);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /confirm re-ingest/i })
      ).toBeEnabled()
    );
  });
});

describe("GuidelineChangesDrawer: DiffSummary never claims approved rules are retired", () => {
  it("tells the reviewer approved rules stay active, and never says 'awaiting review'", async () => {
    global.fetch = makeFetch({
      ...BASE_DIFF,
      removed: [
        {
          number: "1.5.9",
          text: "Old rec.",
          section_title: "",
          rules: [
            { rule_id: "r-active-1", description: "Active rule", status: "active" },
            {
              rule_id: "r-pending-1",
              description: "Pending rule",
              status: "pending_review",
            },
          ],
        },
      ],
      possible_moves: [],
    });

    render(
      <GuidelineChangesDrawer
        code="NG12"
        onClose={jest.fn()}
        onConfirmIngest={jest.fn()}
      />
    );

    await screen.findByText(/already-approved rule/i, undefined, { timeout: 3000 });

    expect(
      screen.getByText(/1 already-approved rule will stay active/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/1 rule awaiting review will be archived/i)).toBeInTheDocument();

    // The old, misleading copy must never appear again.
    expect(screen.queryByText(/will move to awaiting review/i)).not.toBeInTheDocument();
  });

  it("says nothing about approved rules when only pending rules are affected", async () => {
    global.fetch = makeFetch({
      ...BASE_DIFF,
      removed: [
        {
          number: "1.5.9",
          text: "Old rec.",
          section_title: "",
          rules: [
            {
              rule_id: "r-pending-1",
              description: "Pending rule",
              status: "pending_review",
            },
          ],
        },
      ],
      possible_moves: [],
    });

    render(
      <GuidelineChangesDrawer
        code="NG12"
        onClose={jest.fn()}
        onConfirmIngest={jest.fn()}
      />
    );

    await screen.findByText(/1 rule awaiting review will be archived/i, undefined, {
      timeout: 3000,
    });
    expect(screen.queryByText(/already-approved rule/i)).not.toBeInTheDocument();
  });
});
