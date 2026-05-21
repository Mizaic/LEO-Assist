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

/**
 * A single guideline recommendation that matched the patient's presentation.
 * The verbatim text is the exact wording from the NICE guideline document,
 * stored during guideline ingestion. This is what the clinician should see.
 */
export interface GuidelineMatch {
  ruleId: string;
  name: string;
  strength: string;
  guidelineId: string;
  recommendationVerbatim: string | null;
}

/**
 * Referral completeness findings for the patient's referral information.
 * Missing and unclear fields prompt the host system to show a confirmation
 * dialog to the clinician before they proceed.
 */
export interface CompletenessFinding {
  requiredFields: string[];
  presentFields: string[];
  missingFields: string[];
  unclearFields: string[];
}

export interface SbarAssessmentPayload {
  assessmentId: string;
  tenantId: string;
  patientReferenceLabel?: string;
  markdown: string;
  backgroundParts: SbarBackgroundPart[];
  generatedAt: string;
  /** Guideline recommendations that matched this patient's presentation. */
  guidelineMatches?: GuidelineMatch[];
  /**
   * Completeness findings for the referral information.
   * Null means the completeness check has not run yet -- the widget will
   * emit leo:completeness-unavailable so the host can decide what to do.
   */
  completenessFinding?: CompletenessFinding | null;
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
  /**
   * Fires before the widget renders when completeness findings show
   * missing or unclear fields. The host SHOULD show a confirmation dialog.
   */
  completenessIncomplete: "leo:completeness-incomplete",
  /**
   * Fires when no completeness findings are in the payload -- either
   * because the pipeline has not run the check yet, or no schema is
   * configured for this healthcare service.
   */
  completenessUnavailable: "leo:completeness-unavailable",
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
