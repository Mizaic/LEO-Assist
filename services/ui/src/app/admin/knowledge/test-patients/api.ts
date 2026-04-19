/**
 * Thin HTTP client for the centralised Test Patient library.
 *
 * Talks to the existing /api/guidance/test-patients/* surface (the
 * router lives at services/api/app/routers/test_patients.py). The
 * Knowledge tab adds two new endpoints over the legacy guideline
 * library:
 *   - GET    /aspect-counts     -- four count tiles
 *   - GET    /source-patients   -- real-patient picker for clone
 *   - POST   /clone             -- copy real patient as test patient
 *
 * Existing endpoints (list, get, update, delete, replay) are reused
 * verbatim with an extra `aspect` query parameter.
 */

import type {
  AspectCounts,
  AspectFilter,
  CloneResult,
  SourcePatientPickerEntry,
  TestPatientRow,
} from "./types";

const BASE = "/api/guidance/test-patients";

const JSON_HEADERS = {
  "Content-Type": "application/json",
  "X-Requested-With": "XMLHttpRequest",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Request failed (${resp.status})`);
  }
  return (await resp.json()) as T;
}

export function listTestPatients(params: {
  aspect?: AspectFilter;
  guideline_id?: string;
  limit?: number;
}): Promise<TestPatientRow[]> {
  const qs = new URLSearchParams();
  if (params.aspect && params.aspect !== "all") qs.set("aspect", params.aspect);
  if (params.guideline_id) qs.set("guideline_id", params.guideline_id);
  if (params.limit) qs.set("limit", String(params.limit));
  const tail = qs.toString();
  return request(tail ? `?${tail}` : "");
}

export function getAspectCounts(): Promise<AspectCounts> {
  return request("/aspect-counts");
}

export function listSourcePatients(
  limit: number = 50,
): Promise<SourcePatientPickerEntry[]> {
  const qs = new URLSearchParams({ limit: String(limit) });
  return request(`/source-patients?${qs.toString()}`);
}

export interface CloneFromRealBody {
  source_patient_id: string;
  aspect: Exclude<AspectFilter, "all">;
  description?: string;
}

export function cloneFromReal(
  body: CloneFromRealBody,
): Promise<CloneResult> {
  return request("/clone", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export interface BuildBlankBody {
  aspect: "nlp" | "episodes" | "summarisation";
  name: string;
  description?: string;
  age: number | null;
  sex: "male" | "female" | "other" | null;
}

export interface BuildBlankResult {
  id: string;
  name: string;
  aspect: string;
  age: number | null;
  sex: string | null;
}

export function buildBlankTestPatient(
  body: BuildBlankBody,
): Promise<BuildBlankResult> {
  return request("/build", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function deleteTestPatient(id: string): Promise<{ deleted: number }> {
  return request(`/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
}
