/**
 * Live-render tests for the Ask LEO term-expansion dialog:
 * tick stage -> bulk resolve -> confirm mapped criteria.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ConceptExpandDialog from "../ConceptExpandDialog";

function mockApis(terms: string[], searchMap: Record<string, unknown[]>) {
  jest.spyOn(global, "fetch").mockImplementation((url, init) => {
    const href = String(url);
    if (href.includes("/api/guidance/concepts/expand-topic")) {
      expect(init?.method).toBe("POST");
      return Promise.resolve({
        ok: true,
        json: async () => ({ terms, reason: "ok" }),
      } as Response);
    }
    if (href.includes("/api/terminology/search")) {
      const q = new URL(href, "http://local").searchParams.get("q") ?? "";
      return Promise.resolve({
        ok: true,
        json: async () => searchMap[q] ?? [],
      } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => [] } as Response);
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("ConceptExpandDialog", () => {
  it("loads ideas, bulk-resolves ticked terms, and confirms matched criteria", async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn();
    mockApis(["cough", "mystery"], {
      cough: [
        {
          snomed_concept_id: "49727002",
          term: "Cough (finding)",
          semantic_tag: "finding",
        },
      ],
      mystery: [],
    });

    render(
      <ConceptExpandDialog
        open
        phrase="symptoms of lung cancer"
        onClose={jest.fn()}
        onConfirm={onConfirm}
      />,
    );

    expect(
      await screen.findByText(/LEO suggested these terms/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Tick cough/i)).toBeChecked();
    expect(screen.getByLabelText(/Tick mystery/i)).toBeChecked();

    await user.click(screen.getByRole("button", { name: /look up ticked terms/i }));

    expect(await screen.findByText(/Check each match/i)).toBeInTheDocument();
    expect(screen.getByText("Cough (finding)")).toBeInTheDocument();
    expect(screen.getByText(/No match found/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /add the matched/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm.mock.calls[0][0]).toEqual([
      {
        snomed_concept_id: "49727002",
        preferred_term: "Cough (finding)",
        semantic_tag: "finding",
        term: "Cough (finding)",
      },
    ]);
  });

  it("shows an empty-ideas state when LEO returns no terms", async () => {
    mockApis([], {});
    render(
      <ConceptExpandDialog
        open
        phrase="not a clinical topic"
        onClose={jest.fn()}
        onConfirm={jest.fn()}
      />,
    );
    expect(
      await screen.findByText(/did not suggest any terms/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /look up ticked terms/i }),
    ).toBeDisabled();
  });

  it("lets the reviewer change a multi-match pick before adding", async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn();
    mockApis(["cough"], {
      cough: [
        {
          snomed_concept_id: "1",
          term: "Cough",
          semantic_tag: "finding",
        },
        {
          snomed_concept_id: "2",
          term: "Productive cough",
          semantic_tag: "finding",
        },
      ],
    });

    render(
      <ConceptExpandDialog
        open
        phrase="symptoms of lung cancer"
        onClose={jest.fn()}
        onConfirm={onConfirm}
      />,
    );
    await screen.findByText(/LEO suggested these terms/i);
    await user.click(screen.getByRole("button", { name: /look up ticked terms/i }));
    expect(await screen.findByText(/Pick the best match/i)).toBeInTheDocument();

    const select = screen.getByLabelText(/Match for cough/i);
    await user.click(select);
    const listbox = await screen.findByRole("listbox");
    await user.click(within(listbox).getByText("Productive cough"));

    await user.click(screen.getByRole("button", { name: /add the matched/i }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
    expect(onConfirm.mock.calls[0][0][0].snomed_concept_id).toBe("2");
  });
});
