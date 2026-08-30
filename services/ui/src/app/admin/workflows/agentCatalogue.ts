/** Complete catalogue of agents and HITL gates available in the workflow palette. */

import type { AgentDef } from "./types";

export const AGENT_CATALOGUE: AgentDef[] = [
  // -- Automated Agents -------------------------------------------------------
  {
    type: "ers_worklist_consolidated_agent",
    label: "Worklist Processing",
    description: "Polls eRS every 12 hours for new referrals and creates referral records.",
    kind: "ambient",
    interval: 720,
  },
  {
    type: "ers_advice_and_guidance_agent",
    label: "Advice and Guidance",
    description: "Manages eRS Advice and Guidance requests from referring clinicians.",
    kind: "ambient",
    interval: 720,
  },
  {
    type: "ers_advice_and_guidance_download_agent",
    label: "A&G Download",
    description: "Downloads individual Advice and Guidance requests from eRS.",
    kind: "agent",
  },
  {
    type: "ers_referral_download_agent",
    label: "Referral Download",
    description: "Downloads full referral documents and attachments from eRS.",
    kind: "agent",
  },
  {
    type: "ers_response_agent",
    label: "eRS Response",
    description: "Bulk submits referral outcomes back to eRS for a service.",
    kind: "ambient",
    interval: 720,
  },
  {
    type: "referral_prep_agent",
    label: "Referral Preparation",
    description: "Converts referral documents, chunks them, and publishes to the LEO pipeline.",
    kind: "agent",
    interval: 5,
  },
  {
    type: "vectorized_extraction_agent",
    label: "Data Extraction",
    description: "Extracts structured clinical data from referral attachments using vector search.",
    kind: "agent",
  },
  {
    type: "referral_extractor_agent",
    label: "Referral Extractor",
    description: "Extracts structured data from referral letter text.",
    kind: "agent",
  },
  {
    type: "document_mining_extraction_agent",
    label: "Document Mining",
    description: "Deep mining of clinical documents for named entities and clinical facts.",
    kind: "agent",
  },
  {
    type: "appropriateness_agent",
    label: "Appropriateness Check",
    description: "AI check against pathway criteria. Produces an Appropriateness assessment.",
    kind: "agent",
  },
  {
    type: "data_completeness_agent",
    label: "Data Completeness",
    description: "Checks whether all required data extractors have results.",
    kind: "agent",
  },
  {
    type: "classification_agent",
    label: "Classification",
    description: "LLM classifies the referral into a clinical pathway.",
    kind: "agent",
  },
  {
    type: "clinical_summary_agent",
    label: "Clinical Assessment",
    description: "AI clinical triage and SBAR summary generation.",
    kind: "agent",
  },
  {
    type: "leo_assessment_consumer_agent",
    label: "LEO Assessment Consumer",
    description: "Consumes pipeline completion events and advances clinical triage.",
    kind: "agent",
    alwaysTrigger: true,
  },
  {
    type: "medical_record_archive_agent",
    label: "Medical Record Archive",
    description: "Archives completed records for audit and compliance.",
    kind: "agent",
    alwaysTrigger: true,
  },
  {
    type: "reconciliation_agent",
    label: "Reconciliation",
    description: "Reconciles the FHIR A&G worklist against current state in the graph.",
    kind: "agent",
  },
  {
    type: "communications_agent",
    label: "Communications",
    description: "Sends emails and notifications via Microsoft Graph API.",
    kind: "agent",
    alwaysTrigger: true,
  },
  {
    type: "peer_review_agent",
    label: "Peer Review",
    description: "AI peer review of referral against clinical criteria.",
    kind: "agent",
  },

  // -- Human-in-the-Loop Gates ------------------------------------------------
  {
    type: "registration_admin",
    label: "Registration Admin",
    description: "Manual review and validation of referral demographics and registration data.",
    kind: "human",
    statusOnReady: "AWAITING_REGISTRATION_ADMIN",
  },
  {
    type: "clinical_triage",
    label: "Clinical Triage",
    description: "Clinician reviews the referral, AI assessment, and decides appropriate action.",
    kind: "human",
    statusOnReady: "AWAITING_CLINICIAN_REVIEW",
  },
  {
    type: "appointment_manual_booking",
    label: "Appointment Booking",
    description: "Manual scheduling and booking of patient appointments based on clinical priority.",
    kind: "human",
    statusOnReady: "AWAITING_APPOINTMENT_BOOKING",
  },
  {
    type: "clinical_admin",
    label: "Clinical Administrator",
    description: "Administrative oversight and exception handling for referrals needing attention.",
    kind: "human",
    statusOnReady: "NEEDS_ERS_TRIAGE",
    defaultOnHitl: true,
  },
];

export const CATALOGUE_BY_TYPE = Object.fromEntries(
  AGENT_CATALOGUE.map((a) => [a.type, a])
);
