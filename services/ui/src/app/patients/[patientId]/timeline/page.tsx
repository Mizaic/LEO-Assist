/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
"use client";

import { useParams } from "next/navigation";
import PatientTimeline from "@/components/PatientTimeline";

export default function PatientTimelinePage() {
  const { patientId } = useParams<{ patientId: string }>();
  if (!patientId || Array.isArray(patientId)) {
    return <p style={{ padding: 24, color: "#64748b" }}>Invalid patient</p>;
  }
  return <PatientTimeline patientId={patientId} />;
}
