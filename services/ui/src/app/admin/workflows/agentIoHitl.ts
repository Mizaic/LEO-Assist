/** Human-gate I/O and common JSONPath keys used on workflow edges. */

import type { AgentIoContract, IoField, IoKind } from "./agentIo";

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

export const HITL_IO: Record<string, IoSpec> = {
  registration_admin: {
    stateName: "HumanInTheLoop",
    strictness: "bag",
    summary: "Person checks demographics. Writes leo_state.",
    inputs: [ioField("referral", "object", true)],
    outputs: [
      ioField("leo_state", "string", true, "From statusOnReady"),
      ioField("formState", "list"),
    ],
  },
  clinical_triage: {
    stateName: "HumanInTheLoop",
    strictness: "bag",
    summary: "Clinician reviews the AI summary and decides the path.",
    inputs: [
      ioField("sbar_content", "string"),
      ioField("is_appropriate", "boolean"),
      ioField("overall_complete", "boolean"),
    ],
    outputs: [
      ioField("leo_state", "string", true),
      ioField("formState.triageOutcome", "string"),
      ioField("formState.internal_redirect_indicated", "boolean"),
    ],
  },
  appointment_manual_booking: {
    stateName: "HumanInTheLoop",
    strictness: "bag",
    summary: "Person books an appointment. Edges read appointment status.",
    inputs: [ioField("referral", "object", true)],
    outputs: [
      ioField("appointments.status", "string", true, "booked or proposed"),
      ioField("leo_state", "string"),
    ],
  },
  clinical_admin: {
    stateName: "HumanInTheLoop",
    strictness: "bag",
    summary: "Admin exception gate. Default HITL on some services.",
    inputs: [ioField("referral", "object", true)],
    outputs: [ioField("leo_state", "string", true)],
  },
};

export const JOB_CONDITION_KEYS: string[] = [
  "$.appointments[?(@.status=='booked')]",
  "$.appointments[?(@.status=='proposed')]",
  "$.referral[?(@.ers_state=='TRIAGED_PROVIDER_TO_ACTION')]",
  "$.formState[?(@.internal_redirect_indicated=='true')]",
  "$.formState[?(@.triageOutcome=='REJECTED')]",
];
