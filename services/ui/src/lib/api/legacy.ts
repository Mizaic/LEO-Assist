const API_BASE =
  typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE
    ? process.env.NEXT_PUBLIC_API_BASE
    : "http://localhost:8000";

function formatApiError(detail: string | undefined, status: number): string {
  if (detail && detail.length > 0) return detail;
  if (status === 404) return "Not found. Check the ID or return to the list.";
  if (status >= 500) return "Server error. Try again or contact support.";
  return "Request failed. Please try again.";
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { ...init, credentials: "include" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: string }).detail;
    throw new Error(formatApiError(detail, res.status));
  }
  return res.json();
}

export async function fetchPatients() {
  return fetchJson<
    Array<{
      patient_id: string;
      encounter_count: number;
      reviewed_count?: number;
      progress?: number;
    }>
  >(`${API_BASE}/patients`);
}

export async function fetchPatient(patientId: string) {
  return fetchJson<{
    patient_id: string;
    encounter_count: number;
    gender?: string;
    birth_date?: string;
  }>(`${API_BASE}/patients/${patientId}`);
}

export async function fetchPatientEncounters(patientId: string, limit = 500) {
  return fetchJson<
    Array<{ encounter_id: string; date: string; text?: string; coded_count: number; flags?: string }>
  >(`${API_BASE}/patients/${patientId}/encounters?limit=${limit}`);
}

export async function fetchEncounter(patientId: string, encounterId: string) {
  return fetchJson<{
    encounter_id: string;
    date: string;
    text: string;
    coded_count: number;
  }>(`${API_BASE}/patients/${patientId}/encounters/${encounterId}`);
}

export async function fetchEncounterCodedLinks(
  patientId: string,
  encounterId: string,
) {
  return fetchJson<import("@/lib/types").CodedLink[]>(
    `${API_BASE}/patients/${patientId}/encounters/${encounterId}/coded-links`,
  );
}

export async function addCodedLink(
  patientId: string,
  encounterId: string,
  body: {
    concept_id: string;
    term?: string;
    read_code?: string;
    semantic_tag?: string;
    evidence?: string;
    modifiers?: Record<string, unknown>;
    context?: Record<string, unknown>;
  },
) {
  return fetchJson<{ added: boolean; concept_id: string }>(
    `${API_BASE}/patients/${patientId}/encounters/${encounterId}/coded-links`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function deleteCodedLink(
  patientId: string,
  encounterId: string,
  conceptId: string,
) {
  return fetchJson<{ deleted: boolean }>(
    `${API_BASE}/patients/${patientId}/encounters/${encounterId}/coded-links/${conceptId}`,
    { method: "DELETE" },
  );
}

export async function recodeCodedLink(
  patientId: string,
  encounterId: string,
  conceptId: string,
  body: {
    new_concept_id: string;
    term?: string;
    read_code?: string;
    semantic_tag?: string;
    modifiers?: Record<string, unknown>;
  },
) {
  return fetchJson<{ recode: boolean; new_concept_id: string }>(
    `${API_BASE}/patients/${patientId}/encounters/${encounterId}/coded-links/${conceptId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export async function updateCodedLinkModifiers(
  patientId: string,
  encounterId: string,
  conceptId: string,
  modifiers: { value?: string | number; unit?: string; reference_range?: string; interpretation?: string },
) {
  return fetchJson<{ concept_id: string; modifiers: Record<string, unknown> }>(
    `${API_BASE}/patients/${patientId}/encounters/${encounterId}/coded-links/${conceptId}/modifiers`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(modifiers),
    },
  );
}

export async function resetPatient(patientId: string) {
  return fetchJson<{ patient_id: string; links_deleted: number }>(
    `${API_BASE}/patients/${patientId}/reset`,
    { method: "POST" },
  );
}

export async function resetReviewQueue(patientId: string) {
  return fetchJson<{ patient_id: string; deleted: number }>(
    `${API_BASE}/patients/${patientId}/reset-review-queue`,
    { method: "POST" },
  );
}

export async function syncGoldToPatient(patientId: string) {
  return fetchJson<{
    patient_id: string;
    encounters_synced: number;
    links_created: number;
    surface_forms_written?: number;
  }>(`${API_BASE}/patients/${patientId}/sync-gold`, { method: "POST" });
}

export async function exportMedSpaCyTraining(body: {
  export_name: string;
  patient_ids?: string[];
}) {
  return fetchJson<{
    export_id: string;
    entity_count: number;
    kb_count: number;
    encounter_count: number;
    export_path?: string;
  }>(`${API_BASE}/exports/medspacy-training`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function cleanPatients(body: {
  patient_ids: string[];
}) {
  return fetchJson<{
    patients_cleaned: number;
    totals: Record<string, number>;
  }>(`${API_BASE}/pipeline/clean-patients`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patient_ids: body.patient_ids }),
  });
}

export async function inferEncounter(
  patientId: string,
  encounterId: string,
  dryRun = true,
) {
  return fetchJson<{
    encounter_id: string;
    entities: Array<{
      text: string;
      span_start: number;
      span_end: number;
      concept_id?: string;
      term?: string;
      confidence?: number;
      semantic_tag?: string;
    }>;
    written: boolean;
    message?: string;
  }>(`${API_BASE}/patients/${patientId}/encounters/${encounterId}/infer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dry_run: dryRun }),
  });
}

export async function fetchTasks(
  status?: string | null,
  patientId?: string | null,
  limit = 500,
) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (patientId) params.set("patient_id", patientId);
  params.set("limit", String(limit));
  return fetchJson<
    Array<{
      task_id: string;
      candidate_id: string;
      patient_id: string;
      encounter_id: string;
      priority: number;
      status: string;
      warning_count: number;
      created_at: string;
      updated_at: string;
    }>
  >(`${API_BASE}/review/tasks?${params}`);
}

export async function fetchTaskDetail(taskId: string) {
  return fetchJson<{
    task: {
      task_id: string;
      candidate_id: string;
      patient_id: string;
      encounter_id: string;
      priority: number;
      status: string;
      warning_count: number;
      created_at: string;
      updated_at: string;
    };
    candidate: import("../types").EncounterCandidate;
  }>(`${API_BASE}/review/tasks/${taskId}`);
}

export async function submitDecision(
  taskId: string,
  body: {
    action: string;
    reviewer: string;
    reason: string;
    edited_candidate?: unknown;
  },
) {
  return fetchJson<{
    task_id: string;
    candidate_id: string;
    status: string;
    approval_event_id: string;
  }>(`${API_BASE}/review/tasks/${taskId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── Game high scores ───────────────────────────────────────
export type GameName = "snake" | "invaders" | "breakout";

export interface GameScore {
  id: string;
  game: string;
  player: string;
  score: number;
  level: number;
  created_at: string;
  rank: number | null;
}

export async function submitGameScore(body: {
  game: GameName;
  player: string;
  score: number;
  level?: number;
}) {
  return fetchJson<GameScore>(`${API_BASE}/games/scores`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function fetchLeaderboard(game: GameName, limit = 10) {
  return fetchJson<GameScore[]>(
    `${API_BASE}/games/leaderboard?game=${game}&limit=${limit}`,
  );
}

export interface EncounterSearchResult {
  encounter_id: string;
  date: string;
  text?: string;
  coded_count: number;
  flags?: string;
  match_type: "keyword" | "semantic" | "both";
  similarity: number | null;
}

export async function searchPatientEncounters(
  patientId: string,
  q: string,
  mode: "keyword" | "semantic" | "hybrid" = "hybrid",
  limit = 50,
) {
  const params = new URLSearchParams({ q, mode, limit: String(limit) });
  return fetchJson<EncounterSearchResult[]>(
    `${API_BASE}/patients/${patientId}/encounters/search?${params}`,
  );
}

export async function searchTerms(
  q: string,
  limit = 15,
  semanticTags?: string[],
) {
  const params = new URLSearchParams({
    q,
    limit: String(limit),
  });
  if (semanticTags && semanticTags.length > 0) {
    for (const tag of semanticTags) {
      params.append("semantic_tag", tag);
    }
  }
  return fetchJson<
    Array<{
      snomed_concept_id: string;
      term: string;
      read_code?: string;
      semantic_tag?: string;
      score?: number;
    }>
  >(`${API_BASE}/terminology/search?${params}`);
}

export async function fetchSemanticTags() {
  return fetchJson<string[]>(`${API_BASE}/terminology/semantic-tags`);
}

export interface SurfaceFormItem {
  normalized: string;
  form: string;
  source?: string;
  status?: string;
  created_by?: string;
  created_at?: string;
  last_seen_at?: string;
  concept_id: string;
  concept_fsn: string;
  semantic_tag?: string;
  confidence?: number;
  approved_by?: string;
  provenance?: string;
}

export interface SurfaceFormsPage {
  items: SurfaceFormItem[];
  total: number;
  offset: number;
  limit: number;
}

export async function fetchSurfaceForms(
  q?: string,
  conceptId?: string,
  limit = 50,
  offset = 0,
) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (q) params.set("q", q);
  if (conceptId) params.set("concept_id", conceptId);
  return fetchJson<SurfaceFormsPage>(`${API_BASE}/terminology/surface-forms?${params}`);
}

export async function deleteSurfaceForm(normalized: string) {
  return fetchJson<{ deleted: string }>(
    `${API_BASE}/terminology/surface-forms/${encodeURIComponent(normalized)}`,
    { method: "DELETE" },
  );
}

export interface SurfaceFormDuplicate {
  normalized: string;
  form: string;
  concept_count: number;
  rel_count: number;
  mappings: Array<{
    concept_id: string;
    concept_fsn: string;
    confidence?: number;
    provenance?: string;
  }>;
}

export async function fetchSurfaceFormDuplicates() {
  return fetchJson<SurfaceFormDuplicate[]>(`${API_BASE}/terminology/surface-forms/duplicates`);
}

export async function deduplicateSurfaceForms() {
  return fetchJson<{ duplicates_removed: number }>(
    `${API_BASE}/terminology/surface-forms/deduplicate`,
    { method: "POST" },
  );
}

export async function deleteSurfaceFormMapping(normalized: string, conceptId: string) {
  const params = new URLSearchParams({ concept_id: conceptId });
  return fetchJson<{ normalized: string; concept_id: string; removed: number }>(
    `${API_BASE}/terminology/surface-forms/${encodeURIComponent(normalized)}?${params}`,
    { method: "DELETE" },
  );
}

export async function upsertSurfaceFormMapping(
  normalized: string,
  form: string,
  conceptId: string,
  options?: { confidence?: number; provenance?: string; source?: string },
) {
  return fetchJson<{ normalized: string; form: string; concept_id: string; concept_fsn: string }>(
    `${API_BASE}/terminology/surface-forms/upsert-mapping`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        normalized,
        form,
        concept_id: conceptId,
        confidence: options?.confidence ?? 1.0,
        provenance: options?.provenance ?? "manual_correction",
        source: options?.source ?? "manual",
      }),
    },
  );
}

export async function keepSurfaceFormMapping(normalized: string, conceptId: string) {
  const params = new URLSearchParams({ keep_concept_id: conceptId });
  return fetchJson<{ normalized: string; kept_concept_id: string; removed: number }>(
    `${API_BASE}/terminology/surface-forms/${encodeURIComponent(normalized)}?${params}`,
    { method: "DELETE" },
  );
}

export async function fetchDescendants(
  conceptId: string,
  depth = 3,
  semanticTags?: string[],
  limit = 300,
) {
  const params = new URLSearchParams({
    depth: String(depth),
    limit: String(limit),
  });
  if (semanticTags && semanticTags.length > 0) {
    params.append("semantic_tag", semanticTags[0]);
  }
  return fetchJson<
    Array<{
      snomed_concept_id: string;
      term: string;
      semantic_tag?: string;
      surface_form_count: number;
      surface_forms: string[];
    }>
  >(`${API_BASE}/terminology/concepts/${conceptId}/descendants?${params}`);
}
