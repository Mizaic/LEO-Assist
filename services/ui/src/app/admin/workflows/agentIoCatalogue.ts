/**
 * HCCP-Agents LangGraph state, mapped for the workflow builder.
 * Distinctive fields only. Shared handoff (agent_id, next_agents) is omitted.
 */

import type { AgentIoContract, IoField, IoKind } from "./agentIo";
import { HITL_IO } from "./agentIoHitl";

type IoSpec = Omit<AgentIoContract, "agentType">;

function ioField(
  name: string,
  kind: IoKind,
  required = false,
  note?: string,
): IoField {
  if (note === undefined) {
    return { name, kind, required };
  }
  return { name, kind, required, note };
}

export const GENERIC_AGENT_STATE: IoSpec = {
  stateName: "AgentState",
  strictness: "bag",
  summary: "Shared runtime bag used when no agent-specific state exists.",
  inputs: [
    ioField("input_data", "string", true),
    ioField("data", "object", false, "Loose job bag"),
  ],
  outputs: [
    ioField("next_agents", "list"),
    ioField("ids", "list"),
  ],
};

const VEC_EXTRACT: IoSpec = {
  stateName: "VectorizedExtractionAgentState",
  strictness: "bag",
  summary: "Chunks and extractors. Results stay as lists of dicts.",
  inputs: [
    ioField("input_data", "object", true),
    ioField("all_markdown", "string"),
    ioField("chunks", "list"),
    ioField("job", "object", false, "Alias of data for edge conditions"),
  ],
  outputs: [
    ioField("extractors", "list"),
    ioField("extraction_results", "list"),
    ioField("resources", "list"),
    ioField("extracted_document_ids", "list"),
  ],
};

export const AGENT_IO_BY_TYPE: Record<string, IoSpec> = {
  ers_worklist_consolidated_agent: {
    stateName: "AgentState",
    strictness: "bag",
    summary: "Polls eRS and writes new referral records.",
    inputs: [
      ioField("input_data", "string", true),
      ioField("ods_code", "string"),
    ],
    outputs: [
      ioField("worklists", "list"),
      ioField("updated_ubrns", "list"),
      ioField("successful_patient_ids", "list"),
      ioField("worklist_fetch_succeeded", "boolean"),
    ],
  },
  ers_advice_and_guidance_agent: {
    stateName: "ERSAdviceAndGuidanceAgentState",
    strictness: "typed",
    summary: "Fetches Advice and Guidance worklists from eRS.",
    inputs: [
      ioField("input_data", "object", true),
      ioField("service_id", "string"),
      ioField("workflow_id", "string"),
    ],
    outputs: [
      ioField("ag_cases", "list"),
      ioField("ag_requests", "list"),
      ioField("ag_conversations", "list"),
      ioField("pending_ag_responses", "list"),
    ],
  },
  ers_advice_and_guidance_download_agent: {
    stateName: "ErsAdviceAndGuidanceDownloadAgentState",
    strictness: "typed",
    summary: "Downloads one Advice and Guidance request.",
    inputs: [
      ioField("ubrn", "string", true),
      ioField("service_id", "string", true),
    ],
    outputs: [
      ioField("ag_request_data", "object"),
      ioField("conversation_data", "object"),
      ioField("documents_count", "number"),
      ioField("communications_count", "number"),
    ],
  },
  ers_referral_download_agent: {
    stateName: "ErsReferralDownloadAgentState",
    strictness: "typed",
    summary: "Downloads one referral, its appointments, and documents.",
    inputs: [
      ioField("ubrn", "string", true),
      ioField("service_id", "string", true),
    ],
    outputs: [
      ioField("referral_data", "object"),
      ioField("appointments", "list"),
      ioField("documents", "list"),
      ioField("patient_id", "string"),
    ],
  },
  ers_response_agent: {
    stateName: "ERSReferralResponseAgentState",
    strictness: "typed",
    summary: "Posts referral outcomes back to eRS.",
    inputs: [
      ioField("input_data", "object", true),
      ioField("service_id", "string"),
      ioField("workflow_id", "string"),
    ],
    outputs: [
      ioField("pending_referral_outcomes", "list"),
      ioField("already_triaged_skips", "list"),
    ],
  },
  referral_prep_agent: {
    stateName: "VectorizedExtractionAgentState",
    strictness: "typed",
    summary: "Converts documents, chunks them, and starts a LEO run.",
    inputs: [
      ioField("input_data", "object", true),
      ioField("ubrn", "string"),
    ],
    outputs: [
      ioField("combined_markdown", "string"),
      ioField("chunks", "list"),
      ioField("leo_chunk_ids", "list"),
      ioField("leo_run_id", "string"),
      ioField("leo_assessment_status", "string"),
    ],
  },
  vectorized_extraction_agent: VEC_EXTRACT,
  referral_extractor_agent: {
    stateName: "ReferralExtractorAgentState",
    strictness: "bag",
    summary: "Extracts structured fields from referral letter text.",
    inputs: [ioField("input_data", "string", true)],
    outputs: [ioField("data", "object")],
  },
  document_mining_extraction_agent: {
    stateName: "DocumentMiningAgentState",
    strictness: "typed",
    summary: "Mines named entities and clinical facts from documents.",
    inputs: [
      ioField("data", "object", true, "Job bag from Neo4j"),
      ioField("all_markdown", "string"),
    ],
    outputs: [
      ioField("extracted_entities", "object"),
      ioField("mining_results", "object"),
      ioField("resources", "list"),
      ioField("tagged_chunks", "list"),
    ],
  },
  appropriateness_agent: {
    stateName: "AppropriatenessResult",
    strictness: "pydantic",
    summary: "Pathway fit. Writes an Appropriateness node.",
    inputs: [
      ioField("extractors", "list"),
      ioField("job", "object"),
    ],
    outputs: [
      ioField("is_appropriate", "boolean", true),
      ioField("confidence_score", "number", true),
      ioField("criteria_results", "list", true),
      ioField("missing_criteria", "list"),
      ioField("reasoning", "string"),
    ],
  },
  data_completeness_agent: {
    stateName: "VectorizedExtractionAgentState",
    strictness: "bag",
    summary: "Checks that required extractors have results.",
    inputs: [ioField("extractors", "list", true)],
    outputs: [ioField("completeness_results", "object")],
  },
  classification_agent: {
    stateName: "ClassificationAgentState",
    strictness: "typed",
    summary: "Classifies the referral into a pathway name.",
    inputs: [ioField("input_data", "string", true)],
    outputs: [
      ioField("classification", "string"),
      ioField("llm_result", "object"),
    ],
  },
  clinical_summary_agent: {
    stateName: "ClinicalSummaryAgentState",
    strictness: "typed",
    summary: "Builds an SBAR summary and triage flags.",
    inputs: [
      ioField("referral_id", "string"),
      ioField("patient_id", "string"),
      ioField("service_name", "string"),
      ioField("job", "object"),
    ],
    outputs: [
      ioField("situation_markdown", "string"),
      ioField("background_markdown", "string"),
      ioField("assessment_markdown", "string"),
      ioField("recommendation_markdown", "string"),
      ioField("is_appropriate", "boolean"),
      ioField("overall_complete", "boolean"),
      ioField("stt", "boolean"),
      ioField("rtr", "boolean"),
    ],
  },
  leo_assessment_consumer_agent: {
    stateName: "AgentState",
    strictness: "bag",
    summary: "Consumes pipeline completion events and advances triage.",
    inputs: [ioField("completion_events", "list", true)],
    outputs: [ioField("triggered_ubrns", "list")],
  },
  medical_record_archive_agent: {
    stateName: "MedicalRecordArchiveAgentState",
    strictness: "bag",
    summary: "Archives the completed record. Often always-triggers.",
    inputs: [
      ioField("job", "object", true),
      ioField("ubrn", "string", true),
    ],
    outputs: [
      ioField("data_request", "object"),
      ioField("pubsub_result", "object"),
    ],
  },
  reconciliation_agent: {
    stateName: "AgentState",
    strictness: "bag",
    summary: "Reconciles the eRS worklist with the graph.",
    inputs: [ioField("worklists", "list")],
    outputs: [ioField("updated_ubrns", "list")],
  },
  communications_agent: {
    stateName: "CommunicationsAgentState",
    strictness: "typed",
    summary: "Sends email through Microsoft Graph.",
    inputs: [ioField("input_data", "object", true, "Message from Service Bus")],
    outputs: [
      ioField("email_sent", "boolean"),
      ioField("tracking_id", "string"),
    ],
  },
  peer_review_agent: {
    stateName: "PeerReview",
    strictness: "typed",
    summary: "Peer review against clinical criteria.",
    inputs: [
      ioField("input_data", "string", true),
      ioField("data", "object"),
    ],
    outputs: [
      ioField("standardized_assessment", "object", true, "PatientAssessment"),
      ioField("flattened_result", "object"),
    ],
  },
  ...HITL_IO,
};

export { JOB_CONDITION_KEYS } from "./agentIoHitl";
