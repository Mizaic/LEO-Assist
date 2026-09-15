/**
 * Loads the EPR detail, timeline, and coded facts for one patient.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */

import { useEffect, useState } from "react";
import type {
  CodedEntityRow,
  PatientDetail,
  TimelineItem,
} from "@/lib/patientEprApi";
import {
  fetchCodedEntities,
  fetchEprPatientDetail,
  fetchEprPatientTimeline,
} from "@/lib/patientEprApi";

export function usePatientRecord(patientId: string) {
  const [detail, setDetail] = useState<PatientDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [entities, setEntities] = useState<CodedEntityRow[]>([]);
  const [detailLoading, setDetailLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(true);
  const [entitiesLoading, setEntitiesLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [entitiesError, setEntitiesError] = useState<string | null>(null);

  useEffect(() => {
    setDetailLoading(true);
    setDetailError(null);
    fetchEprPatientDetail(patientId)
      .then(setDetail)
      .catch((e) =>
        setDetailError(
          e instanceof Error ? e.message : "Unable to load patient.",
        ),
      )
      .finally(() => setDetailLoading(false));
  }, [patientId]);

  useEffect(() => {
    setTimelineLoading(true);
    setTimelineError(null);
    fetchEprPatientTimeline(patientId)
      .then((data) => setTimeline(Array.isArray(data) ? data : []))
      .catch((e) =>
        setTimelineError(
          e instanceof Error ? e.message : "Unable to load the timeline.",
        ),
      )
      .finally(() => setTimelineLoading(false));
  }, [patientId]);

  useEffect(() => {
    setEntitiesLoading(true);
    setEntitiesError(null);
    fetchCodedEntities(patientId)
      .then(setEntities)
      .catch((e) =>
        setEntitiesError(
          e instanceof Error ? e.message : "Unable to load coded facts.",
        ),
      )
      .finally(() => setEntitiesLoading(false));
  }, [patientId]);

  return {
    detail,
    timeline,
    entities,
    detailLoading,
    timelineLoading,
    entitiesLoading,
    detailError,
    timelineError,
    entitiesError,
  };
}
