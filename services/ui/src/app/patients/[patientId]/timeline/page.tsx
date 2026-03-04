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
