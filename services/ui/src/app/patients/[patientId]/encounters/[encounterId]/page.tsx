"use client";

import { useParams } from "next/navigation";
import ReviewView from "@/components/ReviewView";

export default function ReviewPage() {
  const { patientId, encounterId } = useParams<{ patientId: string; encounterId: string }>();
  return <ReviewView taskId={encounterId} patientId={patientId} />;
}
