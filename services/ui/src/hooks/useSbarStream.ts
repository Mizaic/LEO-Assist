/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
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
  /** Friendly stage error surfaced via sbar_stage_completed.error. */
  errorDetail?: SbarErrorDetail | null;
  /** Friendly stage notice surfaced via sbar_stage_completed.notice. */
  notice?: SbarNotice | null;
  /** Latest per-part progress event for this stage. Currently only
   *  Background emits these (one event per partitioned LLM call) so
   *  the UI can show "Generating Background (part 2 of 5)..." while
   *  the run is still in flight. */
  partProgress?: SbarStagePartProgress | null;
}

/** Per-part progress event emitted while a stage that fans out to
 *  multiple LLM calls (Background today) is mid-flight. The phase
 *  is "map" for the per-part call. There is intentionally no
 *  reduce phase: parts are stitched deterministically in pure
 *  Python so the LLM cannot drop or distort content. */
export interface SbarStagePartProgress {
  stage: SbarStageName;
  phase: "map";
  partIndex: number;
  partTotal: number;
  recordCount: number;
  status: "started" | "completed" | "failed";
  errorCode: string | null;
}

/** Friendly per-stage error built by libs.sbar.error_messages on the
 *  pipeline worker. The `message` field is plain English at reading
 *  age 9-11 and is safe to render directly in the UI. Raw AWS /
 *  Bedrock exception strings are NEVER carried in this shape. */
export interface SbarErrorDetail {
  stage: SbarStageName;
  code: string;
  message: string;
}

/** Friendly per-stage notice (e.g. the background shrinker's
 *  "trimmed N records to fit" message). Same wire shape as
 *  SbarErrorDetail. */
export interface SbarNotice {
  stage: SbarStageName;
  code: string;
  message: string;
}

export interface SbarStreamState {
  running: boolean;
  status: string | null;
  error: string | null;
  runId: string | null;
  assessmentId: string | null;
  stages: Record<SbarStageName, SbarStageState>;
  finalContent: string | null;
  /** Plain-English run errors aggregated on sbar_completed. */
  errors: SbarErrorDetail[];
  /** Plain-English notices aggregated on sbar_completed (e.g.
   *  background trim notice from the shrinker). */
  notices: SbarNotice[];
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
    errors: [],
    notices: [],
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
      errors: [],
      notices: [],
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

    on("sbar_stage_progress", (d) => {
      const stage = (d.stage ?? "") as SbarStageName;
      if (!STAGES.includes(stage)) return;
      const partIndex = Number(d.part_index ?? 0);
      const partTotal = Number(d.part_total ?? 0);
      const partStatus = (d.status ?? "started") as
        | "started"
        | "completed"
        | "failed";
      const progress: SbarStagePartProgress = {
        stage,
        phase: "map",
        partIndex,
        partTotal,
        recordCount: Number(d.record_count ?? 0),
        status: partStatus,
        errorCode:
          typeof d.error_code === "string" ? d.error_code : null,
      };
      const label =
        partStatus === "started"
          ? `Generating ${stage} (part ${partIndex} of ${partTotal})...`
          : partStatus === "failed"
            ? `${stage} part ${partIndex} of ${partTotal} failed.`
            : `${stage} part ${partIndex} of ${partTotal} ready.`;
      setState((s) => ({
        ...s,
        status: label,
        stages: {
          ...s.stages,
          [stage]: { ...s.stages[stage], partProgress: progress },
        },
      }));
    });

    on("sbar_stage_completed", (d) => {
      const stage = (d.stage ?? "") as SbarStageName;
      if (!STAGES.includes(stage)) return;
      const stageError = (d.error ?? null) as SbarErrorDetail | null;
      const stageNotice = (d.notice ?? null) as SbarNotice | null;
      setState((s) => {
        const nextNotices = stageNotice
          ? [...s.notices, stageNotice]
          : s.notices;
        return {
          ...s,
          status: `${stage} ready.`,
          notices: nextNotices,
          stages: {
            ...s.stages,
            [stage]: {
              status: "completed",
              preview: d.preview ?? null,
              ruleCount: d.rule_count,
              actionCount: d.action_count,
              sourceCount: d.source_count,
              codeCount: d.code_count,
              errorDetail: stageError,
              notice: stageNotice,
            },
          },
        };
      });
    });

    on("sbar_completed", async (d) => {
      finishedRef.current = true;
      const errorsList = Array.isArray(d.errors)
        ? (d.errors as SbarErrorDetail[])
        : [];
      const noticesList = Array.isArray(d.notices)
        ? (d.notices as SbarNotice[])
        : [];
      setState((s) => {
        const haveStageNotices = s.notices.length > 0;
        return {
          ...s,
          running: false,
          status:
            d.status === "completed"
              ? "Done."
              : `Done (${d.error_count ?? errorsList.length} errors).`,
          errors: errorsList,
          notices: haveStageNotices ? s.notices : noticesList,
        };
      });
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
        errors: [],
        notices: [],
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
