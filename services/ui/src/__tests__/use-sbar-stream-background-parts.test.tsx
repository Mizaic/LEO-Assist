/**
 * DI-740BE510 -- useSbarStream surfaces structured Background parts.
 *
 * Pins two wires:
 *   1. Per-part source-records summary arriving on the
 *      ``sbar_stage_completed`` SSE event for the Background stage
 *      lands on ``state.backgroundParts`` with snake_case wire fields
 *      mapped to camelCase.
 *   2. ``sbar_completed`` triggers a GET /sbar/assessments/{id} fetch
 *      whose ``background_parts`` payload re-confirms the same shape
 *      (so a page refresh does not lose the disclosure data).
 *
 * Source IDs MUST never be inlined into the rendered markdown; the
 * structured channel is the only carrier the renderer trusts.
 */
import { act, renderHook } from "@testing-library/react";
import { useSbarStream } from "../hooks/useSbarStream";

type EventListener = (e: { data: string }) => void;

class FakeEventSource {
  url: string;
  onerror: (() => void) | null = null;
  private listeners: Record<string, EventListener[]> = {};
  constructor(url: string) {
    this.url = url;
  }
  addEventListener(name: string, fn: EventListener): void {
    (this.listeners[name] ??= []).push(fn);
  }
  close(): void {
    /* no-op for the test */
  }
  /** Test helper: dispatch a parsed SSE event by name. */
  dispatch(name: string, payload: unknown): void {
    const data = JSON.stringify(payload);
    for (const fn of this.listeners[name] ?? []) {
      fn({ data });
    }
  }
}

const STREAM_PARTS = [
  {
    index: 1,
    total: 2,
    record_count: 3,
    record_range: [1, 3],
    source_ids: ["enc-1", "enc-2", "enc-3"],
    status: "completed",
    error_code: null,
    error_message: null,
  },
  {
    index: 2,
    total: 2,
    record_count: 2,
    record_range: [4, 5],
    source_ids: ["enc-4", "enc-5"],
    status: "completed",
    error_code: null,
    error_message: null,
  },
];

const GET_PARTS = STREAM_PARTS; // canonical stored copy

describe("useSbarStream -- DI-740BE510 backgroundParts threading", () => {
  let realES: unknown;
  let realFetch: typeof fetch;
  let postedFetch: jest.Mock;
  let getFetch: jest.Mock;
  let lastEventSource: FakeEventSource | null = null;

  beforeEach(() => {
    realES = (global as unknown as { EventSource: unknown }).EventSource;
    realFetch = global.fetch;

    postedFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: "run-1", assessment_id: "asm-1" }),
      text: async () => "",
    });
    getFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        content: "# SBAR\n\n## Background\n\nbody",
        background_parts: GET_PARTS,
      }),
      text: async () => "",
    });

    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn(
      (url: string, init?: RequestInit) => {
        if (url === "/api/sbar/jobs") {
          return postedFetch(url, init);
        }
        if (url.startsWith("/api/sbar/assessments/")) {
          return getFetch(url, init);
        }
        return Promise.reject(new Error(`unexpected fetch: ${url}`));
      },
    );

    lastEventSource = null;
    (global as unknown as { EventSource: typeof FakeEventSource }).EventSource =
      class extends FakeEventSource {
        constructor(url: string) {
          super(url);
          lastEventSource = this;
        }
      };
  });

  afterEach(() => {
    (global as unknown as { fetch: typeof fetch }).fetch = realFetch;
    (global as unknown as { EventSource: unknown }).EventSource = realES;
  });

  async function startAndConnect(
    result: { current: ReturnType<typeof useSbarStream> },
  ): Promise<FakeEventSource> {
    await act(async () => {
      await result.current.start({
        patientId: "patient-1",
        artifacts: [{ type: "patient_context", id: "patient-1" }],
        background: [{ type: "encounter", id: "enc-1" }],
      });
    });
    expect(lastEventSource).not.toBeNull();
    return lastEventSource!;
  }

  it("populates backgroundParts from the sbar_stage_completed event", async () => {
    const { result } = renderHook(() => useSbarStream());
    const es = await startAndConnect(result);

    expect(result.current.backgroundParts).toEqual([]);

    act(() => {
      es.dispatch("sbar_stage_completed", {
        type: "sbar_stage_completed",
        stage: "background",
        assessment_id: "asm-1",
        preview: "...",
        parts: STREAM_PARTS,
      });
    });

    expect(result.current.backgroundParts).toHaveLength(2);
    expect(result.current.backgroundParts[0]).toEqual({
      index: 1,
      total: 2,
      recordCount: 3,
      recordRange: [1, 3],
      sourceIds: ["enc-1", "enc-2", "enc-3"],
      status: "completed",
      errorCode: null,
      errorMessage: null,
    });

    act(() => {
      result.current.cancel();
    });
  });

  it("does not overwrite backgroundParts when a non-Background stage completes", async () => {
    const { result } = renderHook(() => useSbarStream());
    const es = await startAndConnect(result);

    act(() => {
      es.dispatch("sbar_stage_completed", {
        type: "sbar_stage_completed",
        stage: "background",
        assessment_id: "asm-1",
        parts: STREAM_PARTS,
      });
    });
    expect(result.current.backgroundParts).toHaveLength(2);

    act(() => {
      es.dispatch("sbar_stage_completed", {
        type: "sbar_stage_completed",
        stage: "recommendation",
        assessment_id: "asm-1",
      });
    });
    // Recommendation completion must NOT clear Background's parts.
    expect(result.current.backgroundParts).toHaveLength(2);

    act(() => {
      result.current.cancel();
    });
  });

  it("re-confirms backgroundParts from GET /sbar/assessments/{id} on sbar_completed", async () => {
    const { result } = renderHook(() => useSbarStream());
    const es = await startAndConnect(result);

    await act(async () => {
      es.dispatch("sbar_completed", {
        type: "sbar_completed",
        assessment_id: "asm-1",
        status: "completed",
      });
      // Allow the async GET inside the handler to resolve.
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(getFetch).toHaveBeenCalledWith(
      "/api/sbar/assessments/asm-1",
      undefined,
    );
    expect(result.current.backgroundParts).toHaveLength(2);
    expect(
      result.current.backgroundParts.map((p) => p.sourceIds),
    ).toEqual([
      ["enc-1", "enc-2", "enc-3"],
      ["enc-4", "enc-5"],
    ]);
    expect(result.current.finalContent).toContain("## Background");
  });
});
