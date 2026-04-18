/**
 * VT-LEO-AI-232 -- BackgroundSourcePicker unified feed (live-render layer)
 *
 * Verifies that the picker behaves like the Mission Control encounter
 * text drawer (DI-LEO-AI-179, DI-LEO-AI-213) extended with selection:
 *   - encounters and DocumentReferences appear together in one
 *     chronological feed (no Tabs)
 *   - the kind ToggleButtonGroup narrows the feed to a single kind
 *   - the free-text search box filters records by snippet text
 *   - selection state survives a kind-toggle round-trip
 *   - the running selection count is visible in the header chip
 */
import "@testing-library/jest-dom";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  BackgroundSourcePicker,
  type SelectedBackgroundSource,
} from "@/components/sbar-playground/BackgroundSourcePicker";

jest.mock("@/lib/analyticsApi", () => ({
  __esModule: true,
  listPatientEncounters: jest.fn().mockResolvedValue([
    {
      id: "enc-asthma",
      date: "2026-03-10",
      encounter_type: "Consultation",
      top_concept: "Asthma review",
      coded_count: 3,
      text: "Patient seen for asthma review, peak flow 380.",
    },
    {
      id: "enc-bp",
      date: "2026-02-02",
      encounter_type: "Consultation",
      top_concept: "Hypertension follow-up",
      coded_count: 1,
      text: "Hypertension follow-up: BP today 152/94, repeat in 2 weeks.",
    },
  ]),
  listPatientDocumentReferences: jest.fn().mockResolvedValue([
    {
      id: "doc-letter",
      date: "2026-01-15",
      document_type: "Letter",
      source: "Hospital",
      chunk_count: 2,
      text: "Outpatient letter from cardiology re: hypertension management.",
    },
  ]),
  listDocumentReferenceChunks: jest.fn().mockResolvedValue([
    { id: "chunk-1", ordinal: 0, preview: "Cardiology summary" },
  ]),
}));

describe("VT-LEO-AI-232 BackgroundSourcePicker unified feed", () => {
  function renderPicker() {
    const onConfirm = jest.fn();
    const onClose = jest.fn();
    render(
      <BackgroundSourcePicker
        open
        patientId="patient-1"
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    );
    return { onConfirm, onClose };
  }

  it("shows encounters AND letters together in one feed (no Tabs)", async () => {
    renderPicker();
    expect(
      await screen.findByTestId("background-source-encounter-enc-asthma"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("background-source-encounter-enc-bp"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("background-source-doc-doc-letter"),
    ).toBeInTheDocument();
  });

  it("kind toggle narrows the feed to a single kind", async () => {
    renderPicker();
    await screen.findByTestId("background-source-encounter-enc-asthma");
    const user = userEvent.setup();

    const toggle = screen.getByTestId("background-source-picker-kind-toggle");
    await user.click(within(toggle).getByTestId("kind-toggle-documents"));

    expect(
      screen.queryByTestId("background-source-encounter-enc-asthma"),
    ).toBeNull();
    expect(
      screen.getByTestId("background-source-doc-doc-letter"),
    ).toBeInTheDocument();

    await user.click(within(toggle).getByTestId("kind-toggle-encounters"));
    expect(
      screen.getByTestId("background-source-encounter-enc-asthma"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("background-source-doc-doc-letter"),
    ).toBeNull();
  });

  it("free-text search filters records by snippet text across kinds", async () => {
    renderPicker();
    await screen.findByTestId("background-source-encounter-enc-asthma");
    const user = userEvent.setup();

    const searchBox = within(
      screen.getByTestId("background-source-picker-search"),
    ).getByRole("textbox");
    await user.type(searchBox, "hypertension");

    await waitFor(() => {
      expect(
        screen.queryByTestId("background-source-encounter-enc-asthma"),
      ).toBeNull();
    });
    expect(
      screen.getByTestId("background-source-encounter-enc-bp"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("background-source-doc-doc-letter"),
    ).toBeInTheDocument();
  });

  it("'Select all shown' ticks every visible row scoped to the current filter, and Clear wipes selection", async () => {
    const { onConfirm } = renderPicker();
    await screen.findByTestId("background-source-encounter-enc-asthma");
    const user = userEvent.setup();

    // Narrow to encounters only, then bulk-select.
    const toggle = screen.getByTestId("background-source-picker-kind-toggle");
    await user.click(within(toggle).getByTestId("kind-toggle-encounters"));

    const selectAll = screen.getByTestId(
      "background-source-picker-select-all",
    );
    expect(selectAll).not.toBeDisabled();
    await user.click(selectAll);

    expect(screen.getByTestId("background-source-picker-count")).toHaveTextContent(
      "2 picked",
    );
    expect(selectAll).toBeDisabled();

    await user.click(within(toggle).getByTestId("kind-toggle-all"));
    await user.click(screen.getByTestId("background-source-picker-confirm"));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    const emitted: SelectedBackgroundSource[] = onConfirm.mock.calls[0][0];
    expect(
      emitted.filter((e) => e.type === "encounter").map((e) => e.id).sort(),
    ).toEqual(["enc-asthma", "enc-bp"]);
    expect(
      emitted.some((e) => e.type === "document_reference"),
    ).toBe(false);
  });

  it("'Clear selection' wipes encounters, documents and chunks", async () => {
    renderPicker();
    await screen.findByTestId("background-source-encounter-enc-asthma");
    const user = userEvent.setup();

    await user.click(
      screen.getByTestId("background-source-encounter-enc-asthma"),
    );
    await user.click(screen.getByTestId("background-source-doc-doc-letter"));
    expect(screen.getByTestId("background-source-picker-count")).toHaveTextContent(
      "2 picked",
    );

    await user.click(
      screen.getByTestId("background-source-picker-clear-selection"),
    );
    expect(screen.getByTestId("background-source-picker-count")).toHaveTextContent(
      "0 picked",
    );
  });

  it("selection survives a kind-toggle round-trip and emits both kinds on confirm", async () => {
    const { onConfirm } = renderPicker();
    await screen.findByTestId("background-source-encounter-enc-asthma");
    const user = userEvent.setup();

    await user.click(
      screen.getByTestId("background-source-encounter-enc-asthma"),
    );
    await user.click(screen.getByTestId("background-source-doc-doc-letter"));

    expect(screen.getByTestId("background-source-picker-count")).toHaveTextContent(
      "2 picked",
    );

    const toggle = screen.getByTestId("background-source-picker-kind-toggle");
    await user.click(within(toggle).getByTestId("kind-toggle-encounters"));
    expect(screen.getByTestId("background-source-picker-count")).toHaveTextContent(
      "2 picked",
    );

    await user.click(within(toggle).getByTestId("kind-toggle-all"));
    await user.click(screen.getByTestId("background-source-picker-confirm"));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    const emitted: SelectedBackgroundSource[] = onConfirm.mock.calls[0][0];
    expect(emitted).toEqual(
      expect.arrayContaining([
        { type: "encounter", id: "enc-asthma" },
        { type: "document_reference", id: "doc-letter" },
      ]),
    );
  });
});
