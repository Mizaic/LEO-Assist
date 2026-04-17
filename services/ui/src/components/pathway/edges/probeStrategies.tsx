"use client";

/**
 * Probe-strategy registry barrel (Phase 6b-vi decomposition).
 *
 * Each ProbeStrategy now lives in its own focused module under ./probes/.
 * This file is the single registry the rest of the canvas imports from.
 *
 * Public surface (kept stable for consumers — PortEdge, tests):
 *   - PathSegment        : type
 *   - ProbeDetailProps   : type
 *   - ProbeStrategy      : type
 *   - PROBE_STRATEGIES   : Record<subgraphId, ProbeStrategy>
 *   - TargetHint         : React component
 *   - getSubgraphLabel   : helper
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, R-LEO-AI-166, VT-LEO-AI-163.
 */

import { SUBGRAPH_OPTIONS, SUBGRAPH_IO } from "../config/subgraphs";

import {
  C,
  type ProbeStrategy,
} from "./probes/_shared";

import {
  extraction,
  postProcessing,
  terminology,
  tierClassify,
} from "./probes/extraction";

import {
  verification,
  surfaceFormValidation,
  compliance,
  qualityCheck,
  llmQualityCheck,
} from "./probes/verification";

import {
  persist,
  sbar,
  anchorDetect,
  episodeBuild,
  safetyNet,
  nextBestAction,
} from "./probes/persist";

import {
  restConnector,
  queuePublish,
  hitlQueue,
  encounterLoader,
  stagingEnrichment,
  humanReviewGate,
  encounterCodingAgent,
} from "./probes/connectors";

import {
  guidanceRuleExtraction,
  relationLinking,
} from "./probes/guidance";

/* ── re-exported public types (kept for backwards compatibility) ────── */

export type {
  PathSegment,
  ProbeDetailProps,
  ProbeStrategy,
} from "./probes/_shared";

/* ── registry ───────────────────────────────────────────────────────── */

export const PROBE_STRATEGIES: Record<string, ProbeStrategy> = {
  encounter_loader: encounterLoader,
  extraction,
  post_processing: postProcessing,
  extraction_check: llmQualityCheck,
  terminology,
  coding_check: llmQualityCheck,
  tier_classify: tierClassify,
  verification,
  surface_form_validation: surfaceFormValidation,
  compliance,
  quality_check: qualityCheck,
  persist,
  sbar,
  anchor_detect: anchorDetect,
  episode_build: episodeBuild,
  staging_enrichment: stagingEnrichment,
  human_review_gate: humanReviewGate,
  encounter_coding_agent: encounterCodingAgent,
  safety_net: safetyNet,
  next_best_action: nextBestAction,
  rest_connector: restConnector,
  queue_publish: queuePublish,
  guidance_rule_extraction: guidanceRuleExtraction,
  relation_linking: relationLinking,
  hitl_ner_queue: hitlQueue,
  hitl_coding_queue: hitlQueue,
};

/* ── target hint ────────────────────────────────────────────────────── */

/**
 * Fields that the pipeline engine injects from the step's OWN action config
 * (via _build_step_state) rather than needing to arrive from an upstream step.
 * Exclude these from the "missing inputs" wiring check so the probe doesn't
 * raise a false alarm about fields the step self-supplies.
 */
const CONFIG_INJECTED_FIELDS: Record<string, string[]> = {
  persist:    [],
  extraction: ["prompt_config_id", "model_tier"],
  verification: ["prompt_config_id", "model_tier", "max_retries", "confidence_threshold"],
  sbar:         ["prompt_config_id", "model_tier"],
  compliance:   ["prompt_config_id", "model_tier"],
  anchor_detect: ["prompt_config_id", "model_tier"],
  episode_build: ["prompt_config_id", "model_tier"],
  next_best_action: ["prompt_config_id", "model_tier"],
  quality_check:    ["prompt_config_id", "model_tier"],
  guidance_rule_extraction: ["prompt_config_id", "model_tier"],
  encounter_coding_agent: ["mode", "tier", "apply", "max_input_tokens"],
};

export function TargetHint({ targetSubgraphId, producedKeys }: {
  targetSubgraphId: string;
  producedKeys: string[];
}) {
  const io = SUBGRAPH_IO[targetSubgraphId];
  const option = SUBGRAPH_OPTIONS.find(o => o.id === targetSubgraphId);
  if (!io || !option) return null;
  const selfSupplied = new Set(CONFIG_INJECTED_FIELDS[targetSubgraphId] ?? []);
  const needs = io.reads.filter(k => k !== "*" && !selfSupplied.has(k));
  if (needs.length === 0) return null;
  const met = needs.filter(k => producedKeys.includes(k));
  const missing = needs.filter(k => !producedKeys.includes(k));
  return (
    <div style={{
      border: `1px solid ${missing.length > 0 ? C.orange : C.border}`,
      borderRadius: 8, padding: "6px 9px", background: C.bg, fontSize: 10,
    }}>
      <span style={{ color: C.dim }}>→ Next: </span>
      <span style={{ color: C.blue, fontWeight: 700 }}>{option.label}</span>
      {" — "}
      {missing.length > 0
        ? <span style={{ color: C.orange }}>needs {missing.join(", ")} (not found here)</span>
        : <span style={{ color: C.green }}>all {met.length} inputs ready</span>}
    </div>
  );
}

/* ── helper to resolve friendly label ───────────────────────────────── */

export function getSubgraphLabel(id: string): string {
  return SUBGRAPH_OPTIONS.find(o => o.id === id)?.label ?? id;
}
