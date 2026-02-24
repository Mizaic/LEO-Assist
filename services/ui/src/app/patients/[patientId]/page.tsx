"use client";

import { useParams } from "next/navigation";
import EncounterList from "@/components/EncounterList";

export default function EncountersPage() {
  const { patientId } = useParams<{ patientId: string }>();
  if (!patientId || Array.isArray(patientId)) {
    return <p style={{ padding: 24, color: "#64748b" }}>Invalid patient</p>;
  }
  return <EncounterList patientId={patientId} />;
}
