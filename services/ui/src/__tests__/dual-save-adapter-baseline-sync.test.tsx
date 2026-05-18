/**
 * VT-8DFB9DB8 -- useDualSaveAdapter syncs baseline_concept_ids with
 * the latest seed supplied by the host.
 *
 * Atlas trace:
 *   DI: DI-85B110A5
 *   DO: DO-30A82196
 *   VT: VT-8DFB9DB8
 *   Look up via:
 *     get_design_control(dc_type="verification-test", dc_id="VT-8DFB9DB8")
 *
 * Repro for the regression:
 *   - EncounterCard / EncounterPreviewDialog call useDualSaveAdapter
 *     unconditionally on every render. On the first render,
 *     editorContext is null so the host passes a placeholder
 *     `{ baseline_concept_ids: [] }`.
 *   - Once /gold-labels/from-encounter resolves, the host passes the
 *     real seed (e.g. ["A","B"]).
 *   - useRef(initialValue) only honours initialValue on the FIRST
 *     render, so without a sync effect the ref stays at [] forever.
 *   - The first save then POSTs expected_baseline_concept_ids: [],
 *     mismatching the live set, and the API returns HTTP 409 ("Live
 *     coded links changed since the editor opened. Refresh the
 *     encounter and re-apply your edits.") -- so the reviewer cannot
 *     edit any code.
 *
 * This test pins the fix: the hook re-syncs baselineRef whenever the
 * incoming context.baseline_concept_ids actually changes (by sorted
 * value), and continues to advance it from the response after each
 * successful sync.
 */
import { act, renderHook } from "@testing-library/react";

import { useDualSaveAdapter } from "../components/gold-editor/useDualSaveAdapter";

jest.mock("../components/gold-editor/api", () => ({
  __esModule: true,
  syncCodedLinksFromGold: jest.fn(),
}));

import { syncCodedLinksFromGold } from "../components/gold-editor/api";

const syncMock = syncCodedLinksFromGold as jest.MockedFunction<
  typeof syncCodedLinksFromGold
>;

beforeEach(() => {
  syncMock.mockReset();
});

const SAMPLE_ENTITY = {
  text: "asthma",
  label: "finding",
  assertion: "present",
  snomed_concept_id: "195967001",
  snomed_term: "Asthma (disorder)",
};

function lastCallBaseline(): string[] {
  expect(syncMock).toHaveBeenCalled();
  const callArgs = syncMock.mock.calls[syncMock.mock.calls.length - 1][0];
  return callArgs.expected_baseline_concept_ids;
}

describe("VT-8DFB9DB8 - useDualSaveAdapter baseline sync", () => {
  it("AC1: re-renders with a non-empty baseline after the placeholder", async () => {
    const { result, rerender } = renderHook(
      ({ baseline }: { baseline: string[] }) =>
        useDualSaveAdapter({
          labelId: "manual-1",
          context: {
            patient_id: "p-1",
            encounter_id: "e-1",
            baseline_concept_ids: baseline,
          },
        }),
      { initialProps: { baseline: [] as string[] } },
    );

    rerender({ baseline: ["A", "B"] });

    syncMock.mockResolvedValueOnce({
      live_links_added: 0,
      live_links_removed: 0,
      live_links_updated: 1,
      baseline_concept_ids: ["A", "B"],
    });

    await act(async () => {
      await result.current([SAMPLE_ENTITY]);
    });

    expect(lastCallBaseline()).toEqual(["A", "B"]);
  });

  it("AC2: advances the baseline from the response on each successful sync", async () => {
    const { result } = renderHook(() =>
      useDualSaveAdapter({
        labelId: "manual-1",
        context: {
          patient_id: "p-1",
          encounter_id: "e-1",
          baseline_concept_ids: ["A", "B"],
        },
      }),
    );

    syncMock.mockResolvedValueOnce({
      live_links_added: 1,
      live_links_removed: 0,
      live_links_updated: 0,
      baseline_concept_ids: ["B", "C"],
    });
    await act(async () => {
      await result.current([SAMPLE_ENTITY]);
    });
    expect(lastCallBaseline()).toEqual(["A", "B"]);

    syncMock.mockResolvedValueOnce({
      live_links_added: 0,
      live_links_removed: 1,
      live_links_updated: 0,
      baseline_concept_ids: ["C"],
    });
    await act(async () => {
      await result.current([SAMPLE_ENTITY]);
    });
    expect(lastCallBaseline()).toEqual(["B", "C"]);
  });

  it("AC3: re-seeds when the host swaps to a different encounter", async () => {
    type Args = { encounterId: string; baseline: string[] };
    const { result, rerender } = renderHook(
      ({ encounterId, baseline }: Args) =>
        useDualSaveAdapter({
          labelId: "manual-1",
          context: {
            patient_id: "p-1",
            encounter_id: encounterId,
            baseline_concept_ids: baseline,
          },
        }),
      { initialProps: { encounterId: "e-1", baseline: ["A", "B"] } },
    );

    syncMock.mockResolvedValueOnce({
      live_links_added: 0,
      live_links_removed: 0,
      live_links_updated: 1,
      baseline_concept_ids: ["A", "B"],
    });
    await act(async () => {
      await result.current([SAMPLE_ENTITY]);
    });

    rerender({ encounterId: "e-2", baseline: ["X", "Y"] });

    syncMock.mockResolvedValueOnce({
      live_links_added: 0,
      live_links_removed: 0,
      live_links_updated: 1,
      baseline_concept_ids: ["X", "Y"],
    });
    await act(async () => {
      await result.current([SAMPLE_ENTITY]);
    });
    expect(lastCallBaseline()).toEqual(["X", "Y"]);
  });

  it("Defensive: same baseline re-supplied as a new array does not clobber an advanced ref", async () => {
    // Simulates the host re-rendering with an identical-but-fresh
    // array (e.g. [...seed.baseline_concept_ids]) after a successful
    // save -- the ref must keep the advanced value, not snap back.
    const { result, rerender } = renderHook(
      ({ baseline }: { baseline: string[] }) =>
        useDualSaveAdapter({
          labelId: "manual-1",
          context: {
            patient_id: "p-1",
            encounter_id: "e-1",
            baseline_concept_ids: baseline,
          },
        }),
      { initialProps: { baseline: ["A", "B"] } },
    );

    syncMock.mockResolvedValueOnce({
      live_links_added: 0,
      live_links_removed: 0,
      live_links_updated: 1,
      baseline_concept_ids: ["B", "C"],
    });
    await act(async () => {
      await result.current([SAMPLE_ENTITY]);
    });

    rerender({ baseline: ["A", "B"] });

    syncMock.mockResolvedValueOnce({
      live_links_added: 0,
      live_links_removed: 0,
      live_links_updated: 1,
      baseline_concept_ids: ["B", "C"],
    });
    await act(async () => {
      await result.current([SAMPLE_ENTITY]);
    });
    expect(lastCallBaseline()).toEqual(["B", "C"]);
  });
});
