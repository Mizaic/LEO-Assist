"use client";

import { useParams } from "next/navigation";
import EncounterCodedView from "@/components/EncounterCodedView";

export default function EncounterPage() {
  const { patientId, encounterId } = useParams<{ patientId: string; encounterId: string }>();
  if (!patientId || !encounterId || Array.isArray(patientId) || Array.isArray(encounterId)) {
    return <p style={{ padding: 24, color: "#64748b" }}>Invalid patient or encounter</p>;
  }
  return <EncounterCodedView patientId={patientId} encounterId={encounterId} />;
}
