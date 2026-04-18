/**
 * VT-LEO-AI-232 -- BackgroundSourcePicker chunk rules (live-render layer)
 *
 * Verifies the 'chunks drop parent' rule: if a reviewer ticks a
 * chunk under a document that is also ticked at the document level,
 * onConfirm must emit only the chunk entry (the parent
 * DocumentReference is implicitly dropped).
 */
import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  BackgroundSourcePicker,
  type SelectedBackgroundSource,
} from "@/components/sbar-playground/BackgroundSourcePicker";

jest.mock("@/lib/analyticsApi", () => ({
  __esModule: true,
  listPatientEncounters: jest.fn().mockResolvedValue([]),
  listPatientDocumentReferences: jest.fn().mockResolvedValue([
    {
      id: "doc-1",
      date: "2026-04-01",
      document_type: "Letter",
      source: "GP",
      chunk_count: 2,
    },
  ]),
  listDocumentReferenceChunks: jest.fn().mockResolvedValue([
    { id: "chunk-1", ordinal: 0, preview: "First chunk" },
    { id: "chunk-2", ordinal: 1, preview: "Second chunk" },
  ]),
}));

describe("VT-LEO-AI-232 BackgroundSourcePicker chunk rules", () => {
  it("emits only the chunk entry when both the parent doc AND a chunk are ticked", async () => {
    const onConfirm = jest.fn();
    render(
      <BackgroundSourcePicker
        open
        patientId="patient-1"
        onClose={() => undefined}
        onConfirm={onConfirm}
      />,
    );
    const user = userEvent.setup();

    // No more tabs -- the unified feed shows documents directly. Click
    // the document row to tick its parent checkbox, then expand and
    // tick a chunk.
    const docRow = await screen.findByTestId("background-source-doc-doc-1");
    await user.click(docRow);

    const expand = await screen.findByTestId(
      "background-source-doc-toggle-doc-1",
    );
    await user.click(expand);

    const chunkRow = await screen.findByTestId(
      "background-source-chunk-chunk-1",
    );
    await user.click(chunkRow);

    await user.click(screen.getByTestId("background-source-picker-confirm"));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));

    const emitted: SelectedBackgroundSource[] = onConfirm.mock.calls[0][0];
    expect(emitted).toEqual(
      expect.arrayContaining([
        {
          type: "chunk",
          id: "chunk-1",
          parentDocumentReferenceId: "doc-1",
        },
      ]),
    );
    expect(
      emitted.some((e) => e.type === "document_reference" && e.id === "doc-1"),
    ).toBe(false);
  });
});
