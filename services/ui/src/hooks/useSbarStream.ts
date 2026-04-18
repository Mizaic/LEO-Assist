"use client";

/**
 * useSbarStream -- start an SBAR generation job and stream stage events.
 *
 * Mirrors the shape of usePipelineStream but is specific to the SBAR
 * orchestrator's four-stage event vocabulary:
 *   sbar_started -> sbar_stage_started/completed (situation/background/
 *   assessment/recommendation) -> sbar_completed (or sbar_failed /
 *   pipeline_error).
 *
 * Per DI-LEO-AI-194 (AI Summarisation Playground).
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type SbarStageName =
  | "situation"
  | "background"
  | "assessment"
  | "recommendation";

export interface SbarStageState {
  status: "pending" | "running" | "completed" | "failed";
  preview: string | null;
  ruleCount?: number;
  actionCount?: number;
  sourceCount?: number;
  codeCount?: number;
}

export interface SbarStreamState {
  running: boolean;
  status: string | null;
  error: string | null;
  runId: string | null;
  assessmentId: string | null;
  stages: Record<SbarStageName, SbarStageState>;
  finalContent: string | null;
}

export interface SbarSituationArtifactInput {
  type:
    | "patient_context"
    | "referral_request"
    | "procedure_request"
    | "summarisation_context"
    | "fixed_text";
  id?: string;
  text?: string;
  /** Required when type is "summarisation_context". Mirrors the
   * libs/sbar/events.SummarisationContext enum. */
  context_value?: string;
}

export interface SbarStartConcern {
  /** Free-text reviewer concern that gets appended to the Situation
   *  prompt as a QSIR-aligned safety / clinical framing note. */
  text: string;
}

export interface SbarBackgroundSourceInput {
  type: "encounter" | "document_reference" | "chunk";
  id: string;
}

export interface SbarStartParams {
  patientId: string;
  artifacts: SbarSituationArtifactInput[];
  background: SbarBackgroundSourceInput[];
  guidelineIds?: string[];
  /** Optional free-text concern to frame the Situation. */
  concern?: string;
}

const STAGES: SbarStageName[] = [
  "situation",
  "background",
  "assessment",
  "recommendation",
];

// -- Wire-format mappers ---------------------------------------------------
//
// libs/sbar/events.SituationArtifactType / BackgroundSourceType serialise
// as PascalCase node labels ("Encounter", "DocumentReference",
// "PatientContext", ...). The UI uses snake_case identifiers internally.
// Translate at the boundary so neither side has to know about the other.
const ARTIFACT_TYPE_WIRE: Record<SbarSituationArtifactInput["type"], string> = {
  patient_context: "PatientContext",
  referral_request: "ReferralRequest",
  procedure_request: "ProcedureRequest",
  summarisation_context: "SummarisationContext",
  fixed_text: "FixedText",
};

const BACKGROUND_TYPE_WIRE: Record<SbarBackgroundSourceInput["type"], string> =
  {
    encounter: "Encounter",
    document_reference: "DocumentReference",
    chunk: "Chunk",
  };

function toWireArtifact(a: SbarSituationArtifactInput): Record<string, unknown> {
  const out: Record<string, unknown> = { type: ARTIFACT_TYPE_WIRE[a.type] };
  if (a.id !== undefined) out.id = a.id;
  if (a.text !== undefined) out.text = a.text;
  if (a.context_value !== undefined) out.context_value = a.context_value;
  return out;
}

function toWireBackground(
  b: SbarBackgroundSourceInput,
): Record<string, unknown> {
  return { type: BACKGROUND_TYPE_WIRE[b.type], id: b.id };
}

const initialStage: SbarStageState = { status: "pending", preview: null };

function initialStages(): Record<SbarStageName, SbarStageState> {
  return STAGES.reduce(
    (acc, s) => {
      acc[s] = { ...initialStage };
      return acc;
    },
    {} as Record<SbarStageName, SbarStageState>,
  );
}

export function useSbarStream() {
  const [state, setState] = useState<SbarStreamState>({
    running: false,
    status: null,
    error: null,
    runId: null,
    assessmentId: null,
    stages: initialStages(),
    finalContent: null,
  });

  const esRef = useRef<EventSource | null>(null);
  const finishedRef = useRef(false);

  useEffect(() => () => esRef.current?.close(), []);

  const cancel = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setState((s) => ({ ...s, running: false, status: "Cancelled" }));
  }, []);

  const subscribe = useCallback((runId: string, assessmentId: string) => {
    finishedRef.current = false;
    setState({
      running: true,
      status: "Waiting for worker...",
      error: null,
      runId,
      assessmentId,
      stages: initialStages(),
      finalContent: null,
    });

    const origin =
      typeof window !== "undefined" ? window.location.origin : "";
    const source = new EventSource(
      `${origin}/api/sbar/jobs/${encodeURIComponent(runId)}/events`,
    );
    esRef.current = source;

    const on = (name: string, fn: (d: any) => void) =>
      source.addEventListener(name, (e) =>
        fn(JSON.parse((e as MessageEvent).data)),
      );

    on("sbar_started", () =>
      setState((s) => ({ ...s, status: "Generation started." })),
    );

    on("sbar_stage_started", (d) => {
      const stage = (d.stage ?? "") as SbarStageName;
      if (!STAGES.includes(stage)) return;
      setState((s) => ({
        ...s,
        status: `Generating ${stage}...`,
        stages: {
          ...s.stages,
          [stage]: { ...s.stages[stage], status: "running" },
        },
      }));
    });

    on("sbar_stage_completed", (d) => {
      const stage = (d.stage ?? "") as SbarStageName;
      if (!STAGES.includes(stage)) return;
      setState((s) => ({
        ...s,
        status: `${stage} ready.`,
        stages: {
          ...s.stages,
          [stage]: {
            status: "completed",
            preview: d.preview ?? null,
            ruleCount: d.rule_count,
            actionCount: d.action_count,
            sourceCount: d.source_count,
            codeCount: d.code_count,
          },
        },
      }));
    });

    on("sbar_completed", async (d) => {
      finishedRef.current = true;
      setState((s) => ({
        ...s,
        running: false,
        status:
          d.status === "completed"
            ? "Done."
            : `Done (${d.error_count ?? 0} errors).`,
      }));
      source.close();
      esRef.current = null;
      try {
        const id = state.assessmentId ?? d.assessment_id;
        if (id) {
          const res = await fetch(`/api/sbar/assessments/${encodeURIComponent(id)}`);
          if (res.ok) {
            const json = await res.json();
            setState((s) => ({
              ...s,
              finalContent: typeof json.content === "string" ? json.content : null,
            }));
          }
        }
      } catch {
        /* swallow -- SSE already delivered the section previews */
      }
    });

    on("sbar_failed", (d) => {
      finishedRef.current = true;
      setState((s) => ({
        ...s,
        running: false,
        error: d.message ?? "SBAR generation failed",
      }));
      source.close();
      esRef.current = null;
    });

    on("pipeline_error", (d) => {
      finishedRef.current = true;
      setState((s) => ({
        ...s,
        running: false,
        error: d.message ?? "Pipeline error",
      }));
      source.close();
      esRef.current = null;
    });

    source.onerror = () => {
      if (finishedRef.current) return;
      setState((s) => ({
        ...s,
        running: false,
        error: "Connection dropped",
      }));
      source.close();
      esRef.current = null;
    };
  }, [state.assessmentId]);

  const start = useCallback(
    async (params: SbarStartParams) => {
      esRef.current?.close();
      finishedRef.current = false;
      setState({
        running: true,
        status: "Submitting job...",
        error: null,
        runId: null,
        assessmentId: null,
        stages: initialStages(),
        finalContent: null,
      });
      const concern = (params.concern ?? "").trim();
      const body: Record<string, unknown> = {
        situation: {
          patient_id: params.patientId,
          artifacts: params.artifacts.map(toWireArtifact),
        },
        background: params.background.map(toWireBackground),
        guideline_ids: params.guidelineIds ?? [],
      };
      if (concern.length > 0) {
        body.concern = concern;
      }
      let res: Response;
      try {
        res = await fetch("/api/sbar/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } catch (err) {
        setState((s) => ({
          ...s,
          running: false,
          error: `Network error: ${String(err)}`,
        }));
        return;
      }
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        setState((s) => ({
          ...s,
          running: false,
          error: `Failed to start (${res.status}): ${text}`,
        }));
        return;
      }
      const json = await res.json();
      subscribe(String(json.run_id), String(json.assessment_id));
    },
    [subscribe],
  );

  return { ...state, start, subscribe, cancel } as const;
}
