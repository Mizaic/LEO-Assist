/**
 * VTs for DI-5F121122:
 *   VT-D6C11E1B - sink emits disclosure + source-click events     (AC1+AC2)
 *   VT-1D9CF994 - sink exposes no opt-out API                     (AC3)
 *   VT-5D887E30 - sink retries with backoff and surfaces degraded (AC4)
 *
 * Atlas trace:
 *   DO: DO-23DDE984
 *   DI: DI-5F121122
 */

import { TelemetrySink } from "../telemetry/sink";

const ENDPOINT = "https://analytics.example.test/sdk/telemetry";

function _okResponse(): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({ status: "accepted" }),
  } as unknown as Response;
}

async function _flushMicrotasks(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

// ---------------------------------------------------------------------------
// VT-D6C11E1B - AC1 + AC2 sink emits disclosure + source-click events
// ---------------------------------------------------------------------------

describe("VT-D6C11E1B - telemetry sink emits required events", () => {
  test("emits disclosure-opened POST with the expected payload shape", async () => {
    const fetcher = jest.fn().mockResolvedValue(_okResponse());
    const sink = new TelemetrySink({
      analyticsUrl: ENDPOINT,
      assessmentId: "ASSESS-1",
      fetcher: fetcher as unknown as typeof fetch,
    });
    sink.record("disclosure-opened", { stage: "background" });
    await _flushMicrotasks();

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe(ENDPOINT);
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.type).toBe("disclosure-opened");
    expect(body.assessment_id).toBe("ASSESS-1");
    expect(body.payload.stage).toBe("background");
    expect(body.widget_instance_id).toMatch(/^wi-/);
    expect(body.event_id).toBe(1);
  });

  test("emits source-id-clicked carrying the source-id payload", async () => {
    const fetcher = jest.fn().mockResolvedValue(_okResponse());
    const sink = new TelemetrySink({
      analyticsUrl: ENDPOINT,
      assessmentId: "ASSESS-1",
      fetcher: fetcher as unknown as typeof fetch,
    });
    sink.record("source-id-clicked", {
      stage: "background",
      sourceId: "enc-A001",
    });
    await _flushMicrotasks();

    const body = JSON.parse(
      (fetcher.mock.calls[0][1] as RequestInit).body as string,
    );
    expect(body.type).toBe("source-id-clicked");
    expect(body.payload.sourceId).toBe("enc-A001");
  });
});

// ---------------------------------------------------------------------------
// VT-1D9CF994 - AC3 sink exposes no opt-out API
// ---------------------------------------------------------------------------

describe("VT-1D9CF994 - sink exposes no mute / disable / rewrite API", () => {
  const FORBIDDEN = /disable|mute|silence|opt.?out|rewrite|setEndpoint|setUrl/i;

  test("prototype has no method whose name reveals an opt-out", () => {
    const proto = Object.getPrototypeOf(
      new TelemetrySink({
        analyticsUrl: ENDPOINT,
        assessmentId: "A1",
        fetcher: jest.fn().mockResolvedValue(_okResponse()) as unknown as typeof fetch,
      }),
    );
    for (const name of Object.getOwnPropertyNames(proto)) {
      expect(FORBIDDEN.test(name)).toBe(false);
    }
  });

  test("analyticsUrl property is read-only after construction", () => {
    const sink = new TelemetrySink({
      analyticsUrl: ENDPOINT,
      assessmentId: "A1",
      fetcher: jest.fn().mockResolvedValue(_okResponse()) as unknown as typeof fetch,
    });
    expect(() => {
      (sink as unknown as { analyticsUrl: string }).analyticsUrl =
        "https://attacker.example/x";
    }).toThrow();
    expect(sink.analyticsUrl).toBe(ENDPOINT);
  });
});

// ---------------------------------------------------------------------------
// VT-5D887E30 - AC4 sink retries with backoff and surfaces degraded state
// ---------------------------------------------------------------------------

describe("VT-5D887E30 - sink retries on failure and degrades gracefully", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });
  afterEach(() => {
    jest.useRealTimers();
  });

  test("record() does not throw when fetch rejects", () => {
    const fetcher = jest.fn().mockRejectedValue(new Error("network down"));
    const sink = new TelemetrySink({
      analyticsUrl: ENDPOINT,
      assessmentId: "A1",
      fetcher: fetcher as unknown as typeof fetch,
    });
    expect(() => sink.record("loaded")).not.toThrow();
  });

  test(
    "fires onDegraded(true) on failure and onDegraded(false) after recovery",
    async () => {
      const calls: boolean[] = [];
      let succeed = false;
      const fetcher = jest.fn().mockImplementation(async () => {
        if (!succeed) {
          throw new Error("boom");
        }
        return _okResponse();
      });
      const sink = new TelemetrySink({
        analyticsUrl: ENDPOINT,
        assessmentId: "A1",
        fetcher: fetcher as unknown as typeof fetch,
        onDegraded: (d) => calls.push(d),
      });

      sink.record("disclosure-opened", { stage: "background" });
      await Promise.resolve();
      await Promise.resolve();
      expect(calls[0]).toBe(true);
      expect(sink._stateForTesting().queueLength).toBe(1);

      succeed = true;
      jest.advanceTimersByTime(1_500);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();

      expect(calls[calls.length - 1]).toBe(false);
      expect(sink._stateForTesting().queueLength).toBe(0);
    },
  );
});
