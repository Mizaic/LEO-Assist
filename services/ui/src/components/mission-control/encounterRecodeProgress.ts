// Live SSE wiring for the per-encounter "Reset and recode" flow.
// Extracted from EncounterTextTab so the main component stays under
// the 500-LOC ceiling. See DI-LEO-AI-179 / DO-LEO-AI-178.

export type RecodeJobState =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | null;

export type SetRecodeJobState = (state: RecodeJobState) => void;
export type SetRecodeMessage = (message: string | null) => void;

const PROGRESS_EVENT_TYPES = [
  "run_started",
  "patient_started",
  "encounter_started",
  "run_completed",
  "pipeline_done",
  "extraction_done",
  "pipeline_error",
  "run_error",
] as const;

interface ProgressPayload {
  type?: string;
  message?: string;
}

function classifyEvent(
  type: string,
  message: string | undefined,
  setState: SetRecodeJobState,
  setMessage: SetRecodeMessage,
  complete: (next: "completed" | "failed", text: string) => void
): void {
  if (
    type === "run_started" ||
    type === "patient_started" ||
    type === "encounter_started"
  ) {
    setState("running");
    setMessage(`Running: ${message ?? "pipeline is processing this encounter."}`);
    return;
  }
  if (
    type === "run_completed" ||
    type === "extraction_done" ||
    type === "pipeline_done"
  ) {
    complete("completed", "Completed: pipeline finished for this encounter.");
    return;
  }
  if (type === "pipeline_error" || type === "run_error") {
    complete("failed", `Failed: ${message ?? "pipeline execution error."}`);
  }
}

export function waitForRecodeProgress(
  runId: string,
  setRecodeJobState: SetRecodeJobState,
  setRecodeMessage: SetRecodeMessage
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const source = new EventSource(
      `${window.location.origin}/api/pipeline/progress/${encodeURIComponent(runId)}`
    );
    let settled = false;

    const complete = (
      nextState: "completed" | "failed",
      message: string
    ) => {
      if (settled) return;
      settled = true;
      setRecodeJobState(nextState);
      setRecodeMessage(message);
      source.close();
      if (nextState === "completed") resolve();
      else reject(new Error(message));
    };

    const onEvent = (ev: MessageEvent) => {
      try {
        const payload = JSON.parse(ev.data) as ProgressPayload;
        classifyEvent(
          payload.type ?? "",
          payload.message,
          setRecodeJobState,
          setRecodeMessage,
          complete
        );
      } catch {
        // Ignore malformed progress events.
      }
    };

    PROGRESS_EVENT_TYPES.forEach((type) =>
      source.addEventListener(type, onEvent as EventListener)
    );
    source.onerror = () => {
      complete("failed", "Failed: connection to live pipeline status was lost.");
    };
  });
}
