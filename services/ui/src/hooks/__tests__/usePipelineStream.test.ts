import { renderHook, act } from "@testing-library/react";
import { usePipelineStream } from "../usePipelineStream";

type Listener = (e: MessageEvent) => void;

class MockEventSource {
  url: string;
  listeners: Record<string, Listener[]> = {};
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(name: string, fn: Listener) {
    (this.listeners[name] ??= []).push(fn);
  }

  close() {
    this.closed = true;
  }

  emit(name: string, data: Record<string, unknown>) {
    for (const fn of this.listeners[name] ?? []) {
      fn({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  static instances: MockEventSource[] = [];
  static reset() {
    MockEventSource.instances = [];
  }
  static last(): MockEventSource {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }
}

beforeAll(() => {
  (global as any).EventSource = MockEventSource;
});

afterAll(() => {
  delete (global as any).EventSource;
});

beforeEach(() => {
  MockEventSource.reset();
});

describe("usePipelineStream", () => {
  it("returns initial idle state", () => {
    const { result } = renderHook(() => usePipelineStream());
    expect(result.current.running).toBe(false);
    expect(result.current.status).toBeNull();
    expect(result.current.live).toBeNull();
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.workerStates).toEqual({});
  });

  it("start() creates an EventSource with stream URL", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1", "P2"], workers: 2, dryRun: false });
    });
    const es = MockEventSource.last();
    expect(es.url).toContain("/pipeline/stream?");
    expect(es.url).toContain("patient_ids=P1%2CP2");
    expect(es.url).toContain("workers=2");
    expect(es.url).toContain("dry_run=false");
  });

  it("start() with encounterId uses stream-encounter endpoint", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"], encounterId: "E1", dryRun: true });
    });
    const es = MockEventSource.last();
    expect(es.url).toContain("/pipeline/stream-encounter?");
    expect(es.url).toContain("patient_id=P1");
    expect(es.url).toContain("encounter_id=E1");
  });

  it("start() with unprocessedOnly uses stream-unprocessed endpoint", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"], unprocessedOnly: true });
    });
    const es = MockEventSource.last();
    expect(es.url).toContain("/pipeline/stream-unprocessed?");
  });

  it("start() sets running=true and initializes live state", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"] });
    });
    expect(result.current.running).toBe(true);
    expect(result.current.status).toBe("Connecting…");
    expect(result.current.live).toEqual({
      run_id: "starting",
      processed_encounters: 0,
      queued_for_review: 0,
      auto_approved: 0,
      rejected_hard_fail: 0,
      warnings_only: 0,
    });
  });

  it("run_started event updates status", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"] });
    });
    act(() => {
      MockEventSource.last().emit("run_started", { run_id: "R1" });
    });
    expect(result.current.status).toBe("Run started (R1)");
  });

  it("encounter_started updates worker state", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"] });
    });
    act(() => {
      MockEventSource.last().emit("encounter_started", {
        worker_id: 1,
        encounter_id: "E1",
      });
    });
    expect(result.current.workerStates[1]).toEqual({
      workerId: 1,
      step: "load",
      encounterId: "E1",
      statusText: "Loading…",
      completedCount: 0,
    });
  });

  it("encounter_processed increments completedCount and updates live", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"] });
    });
    act(() => {
      MockEventSource.last().emit("encounter_started", { worker_id: 1, encounter_id: "E1" });
    });
    act(() => {
      MockEventSource.last().emit("encounter_processed", {
        worker_id: 1,
        encounter_id: "E1",
        run_id: "R1",
        processed_encounters: 1,
        queued_for_review: 1,
        rejected_hard_fail: 0,
        warnings_only: 0,
      });
    });
    expect(result.current.workerStates[1].step).toBe("done");
    expect(result.current.workerStates[1].completedCount).toBe(1);
    expect(result.current.live?.processed_encounters).toBe(1);
  });

  it("run_completed sets result, stops running, closes source", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"] });
    });
    const es = MockEventSource.last();
    act(() => {
      es.emit("run_completed", {
        run_id: "R1",
        processed_encounters: 5,
        queued_for_review: 3,
        rejected_hard_fail: 1,
        warnings_only: 1,
      });
    });
    expect(result.current.running).toBe(false);
    expect(result.current.status).toBe("Run completed");
    expect(result.current.result).toEqual({
      run_id: "R1",
      processed_encounters: 5,
      queued_for_review: 3,
      auto_approved: 0,
      rejected_hard_fail: 1,
      warnings_only: 1,
      llm_usage: undefined,
    });
    expect(es.closed).toBe(true);
  });

  it("pipeline_error sets error and stops running", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"] });
    });
    const es = MockEventSource.last();
    act(() => {
      es.emit("pipeline_error", { message: "Out of memory" });
    });
    expect(result.current.error).toBe("Out of memory");
    expect(result.current.running).toBe(false);
    expect(es.closed).toBe(true);
  });

  it("cancel() closes source and sets status", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"] });
    });
    const es = MockEventSource.last();
    act(() => {
      result.current.cancel();
    });
    expect(es.closed).toBe(true);
    expect(result.current.running).toBe(false);
    expect(result.current.status).toBe("Cancelled");
  });

  it("connection error sets error when not finished", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"] });
    });
    const es = MockEventSource.last();
    act(() => {
      es.onerror?.();
    });
    expect(result.current.error).toBe("Connection dropped");
    expect(result.current.running).toBe(false);
  });

  it("start() with maxEncountersPerPatient includes param", () => {
    const { result } = renderHook(() => usePipelineStream());
    act(() => {
      result.current.start({ patientIds: ["P1"], maxEncountersPerPatient: 10 });
    });
    const es = MockEventSource.last();
    expect(es.url).toContain("max_encounters_per_patient=10");
  });
});
