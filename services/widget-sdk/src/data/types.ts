/**
 * Shared data contracts for the LEO widget SDK.
 *
 * Atlas trace:
 *   DI: DI-85C95E53 (distribution variants)
 *   Risk mitigated: R-4965BCD2 (AI handover used without clinician review)
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-85C95E53")
 *
 * These types are kept structurally compatible with the canonical
 * SBAR types in
 *   services/ui/src/components/sbar-final/SbarFinalView.tsx
 * so the widget consumes the same wire shape that the SBAR pipeline
 * already emits and that the in-app SbarFinalView already renders. A
 * follow-up DO will hoist those types into a shared package; until
 * then this file is the single source of truth for the SDK side.
 */

export type SbarStageName =
  | "situation"
  | "background"
  | "assessment"
  | "recommendation";

export interface SbarSection {
  stage: SbarStageName;
  body: string;
}

/**
 * Per-partition Background source-record summary. Mirrors the wire
 * shape produced by libs/sbar/prompt_calls.py _build_part_summary
 * and persisted as background_parts on the :Assessment node.
 *
 * The sourceIds list is the safety-critical disclosure payload that
 * mitigates R-4965BCD2: a reviewer must be able to see exactly which
 * encounter records each Background claim was synthesised from.
 */
export interface SbarBackgroundPart {
  index: number;
  total: number;
  recordCount: number;
  recordRange: [number, number];
  sourceIds: string[];
  status: "completed" | "failed";
  errorCode?: string | null;
  errorMessage?: string | null;
}

export interface SbarAssessmentPayload {
  assessmentId: string;
  tenantId: string;
  patientReferenceLabel?: string;
  markdown: string;
  backgroundParts: SbarBackgroundPart[];
  generatedAt: string;
}

/**
 * Lifecycle event names emitted by the widget. Both variants emit
 * structurally identical event payloads:
 *   - web component: dispatched via this.dispatchEvent(new CustomEvent(...))
 *   - iframe       : posted to window.parent via postMessage({type, ...})
 *
 * Hosts MUST treat these names as the stable contract.
 */
export const LEO_EVENT_NAMES = {
  loaded: "leo:loaded",
  error: "leo:error",
  disclosureOpened: "leo:disclosure-opened",
  disclosureClosed: "leo:disclosure-closed",
  sourceClicked: "leo:source-clicked",
} as const;

export type LeoEventName =
  (typeof LEO_EVENT_NAMES)[keyof typeof LEO_EVENT_NAMES];

export interface LeoEventPayload {
  assessmentId: string;
  stage?: SbarStageName;
  sourceId?: string;
  errorCode?: string;
  errorMessage?: string;
}
