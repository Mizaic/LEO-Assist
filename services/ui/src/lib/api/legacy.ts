/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { triggerReauth } from "./client";

const API_BASE =
  typeof window !== "undefined"
    ? window.location.origin
    : (process.env.INTERNAL_API_BASE || "http://localhost:8000").replace(/\/+$/, "");

// Core API paths (patients, review, exports, pipeline, games) must use /api prefix
// in browser so Next.js proxy rewrites to backend. Terminology/training already use /api/.
const CORE_PATH = typeof window !== "undefined" ? "/api" : "";

function formatApiError(detail: string | undefined, status: number): string {
  if (detail && detail.length > 0) return detail;
  if (status === 404) return "Not found. Check the ID or return to the list.";
  if (status >= 500) return "Server error. Try again or contact support.";
  return "Request failed. Please try again.";
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    if (res.status === 401) await triggerReauth();
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
  >(`${API_BASE}${CORE_PATH}/patients`);
}

export async function fetchPatient(patientId: string) {
  return fetchJson<{
    patient_id: string;
    encounter_count: number;
    gender?: string;
    birth_date?: string;
  }>(`${API_BASE}${CORE_PATH}/patients/${patientId}`);
}

export async function fetchPatientEncounters(patientId: string, limit = 500) {
  return fetchJson<
    Array<{ encounter_id: string; date: string; text?: string; coded_count: number; flags?: string }>
  >(`${API_BASE}${CORE_PATH}/patients/${patientId}/encounters?limit=${limit}`);
}

export async function fetchEncounter(patientId: string, encounterId: string) {
  return fetchJson<{
    encounter_id: string;
    date: string;
    text: string;
    coded_count: number;
  }>(`${API_BASE}${CORE_PATH}/patients/${patientId}/encounters/${encounterId}`);
}

export async function fetchEncounterCodedLinks(
  patientId: string,
  encounterId: string,
) {
  return fetchJson<import("@/lib/types").CodedLink[]>(
    `${API_BASE}${CORE_PATH}/patients/${patientId}/encounters/${encounterId}/coded-links`,
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
    `${API_BASE}${CORE_PATH}/patients/${patientId}/encounters/${encounterId}/coded-links`,
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
    `${API_BASE}${CORE_PATH}/patients/${patientId}/encounters/${encounterId}/coded-links/${conceptId}`,
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
    `${API_BASE}${CORE_PATH}/patients/${patientId}/encounters/${encounterId}/coded-links/${conceptId}`,
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
    `${API_BASE}${CORE_PATH}/patients/${patientId}/encounters/${encounterId}/coded-links/${conceptId}/modifiers`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(modifiers),
    },
  );
}

export async function resetPatient(patientId: string) {
  return fetchJson<{ patient_id: string; links_deleted: number }>(
    `${API_BASE}${CORE_PATH}/patients/${patientId}/reset`,
    { method: "POST" },
  );
}

export async function resetReviewQueue(patientId: string) {
  return fetchJson<{ patient_id: string; deleted: number }>(
    `${API_BASE}${CORE_PATH}/patients/${patientId}/reset-review-queue`,
    { method: "POST" },
  );
}

export async function syncGoldToPatient(patientId: string) {
  return fetchJson<{
    patient_id: string;
    encounters_synced: number;
    links_created: number;
    surface_forms_written?: number;
  }>(`${API_BASE}${CORE_PATH}/patients/${patientId}/sync-gold`, { method: "POST" });
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
  }>(`${API_BASE}${CORE_PATH}/exports/medspacy-training`, {
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
  }>(`${API_BASE}${CORE_PATH}/pipeline/clean-patients`, {
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
  }>(`${API_BASE}${CORE_PATH}/patients/${patientId}/encounters/${encounterId}/infer`, {
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
  >(`${API_BASE}${CORE_PATH}/review/tasks?${params}`);
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
  }>(`${API_BASE}${CORE_PATH}/review/tasks/${taskId}`);
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
  }>(`${API_BASE}${CORE_PATH}/review/tasks/${taskId}/decision`, {
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
  return fetchJson<GameScore>(`${API_BASE}${CORE_PATH}/games/scores`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function fetchLeaderboard(game: GameName, limit = 10) {
  return fetchJson<GameScore[]>(
    `${API_BASE}${CORE_PATH}/games/leaderboard?game=${game}&limit=${limit}`,
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
    `${API_BASE}${CORE_PATH}/patients/${patientId}/encounters/search?${params}`,
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
      module_id?: string;
      score?: number;
      from_surface_form?: boolean;
    }>
  >(`${API_BASE}/api/terminology/search?${params}`);
}

export async function fetchSemanticTags() {
  return fetchJson<string[]>(`${API_BASE}/api/terminology/semantic-tags`);
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
  return fetchJson<SurfaceFormsPage>(`${API_BASE}/api/terminology/surface-forms?${params}`);
}

export async function deleteSurfaceForm(normalized: string) {
  return fetchJson<{ deleted: string }>(
    `${API_BASE}/api/terminology/surface-forms/${encodeURIComponent(normalized)}`,
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
  return fetchJson<SurfaceFormDuplicate[]>(`${API_BASE}/api/terminology/surface-forms/duplicates`);
}

export async function deduplicateSurfaceForms() {
  return fetchJson<{ duplicates_removed: number }>(
    `${API_BASE}/api/terminology/surface-forms/deduplicate`,
    { method: "POST" },
  );
}

export async function deleteSurfaceFormMapping(normalized: string, conceptId: string) {
  const params = new URLSearchParams({ concept_id: conceptId });
  return fetchJson<{ normalized: string; concept_id: string; removed: number }>(
    `${API_BASE}/api/terminology/surface-forms/${encodeURIComponent(normalized)}?${params}`,
    { method: "DELETE" },
  );
}

export async function upsertSurfaceFormMapping(
  normalized: string,
  form: string,
  conceptId: string,
  options?: { confidence?: number; provenance?: string; source?: string; actor?: string },
) {
  return fetchJson<{
    normalized: string;
    form: string;
    concept_id: string;
    concept_fsn: string;
    status?: string;
    reviewer?: string;
    reviewed_at?: string;
    effective_at?: string;
  }>(
    `${API_BASE}/api/terminology/surface-forms/upsert-mapping`,
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
        actor: options?.actor ?? "knowledge-admin",
      }),
    },
  );
}

export interface SurfaceFormAuditEntry {
  id: string;
  normalized: string;
  action: string;
  actor: string;
  outcome: string;
  detail?: string;
  concept_id?: string;
  created_at?: string;
}

export interface SurfaceFormAuditPage {
  items: SurfaceFormAuditEntry[];
  total: number;
  offset: number;
  limit: number;
}

export async function fetchSurfaceFormAuditLog(
  normalized?: string,
  limit = 50,
  offset = 0,
): Promise<SurfaceFormAuditPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (normalized) params.set("normalized", normalized);
  return fetchJson<SurfaceFormAuditPage>(
    `${API_BASE}/api/terminology/surface-forms/audit-log?${params}`,
  );
}

export async function approveSurfaceFormMapping(
  normalized: string,
  options?: { reviewer?: string; conceptId?: string },
) {
  return fetchJson<GroupedSurfaceForm & { concept_id: string; concept_fsn: string }>(
    `${API_BASE}/api/terminology/surface-forms/${encodeURIComponent(normalized)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewer: options?.reviewer ?? "knowledge-admin",
        concept_id: options?.conceptId,
      }),
    },
  );
}

export async function deactivateSurfaceFormMapping(
  normalized: string,
  options?: { actor?: string },
) {
  return fetchJson<GroupedSurfaceForm & { concept_id: string; concept_fsn: string }>(
    `${API_BASE}/api/terminology/surface-forms/${encodeURIComponent(normalized)}/deactivate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor: options?.actor ?? "knowledge-admin" }),
    },
  );
}

export interface LabelEntity {
  text: string;
  label: string;
  start?: number;
  end?: number;
  assertion?: string;
  confidence?: number;
  snomed_concept_id?: string;
  semantic_tag?: string;
}

export async function patchLabelEntities(
  labelId: string,
  entities: LabelEntity[],
): Promise<{ label_id: string; entities: LabelEntity[] }> {
  return fetchJson<{ label_id: string; entities: LabelEntity[] }>(
    `${API_BASE}/api/training/labels/${encodeURIComponent(labelId)}/entities`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entities }),
    },
  );
}

export async function patchGoldLabelEntities(
  labelId: string,
  entities: LabelEntity[],
): Promise<{ label_id: string; entities: LabelEntity[] }> {
  return fetchJson<{ label_id: string; entities: LabelEntity[] }>(
    `${API_BASE}/api/training/gold-labels/${encodeURIComponent(labelId)}/entities`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entities }),
    },
  );
}

export interface GoldLabelRecord {
  label_id: string;
  text: string;
  entities_json: string | null;
  quality_score: number | null;
  source: string;
  verified_by: string | null;
  verified_at: string | null;
  candidate_id: string | null;
  updated_at: string;
}

export async function fetchGoldLabel(labelId: string): Promise<GoldLabelRecord> {
  return fetchJson<GoldLabelRecord>(
    `${API_BASE}/api/training/gold-labels/${encodeURIComponent(labelId)}`,
  );
}

export interface RepairSpansResult {
  label_id: string;
  repaired: number;
  dropped: number;
  remaining: number;
}

export async function repairGoldLabelSpans(
  labelId: string,
): Promise<RepairSpansResult> {
  return fetchJson<RepairSpansResult>(
    `${API_BASE}/api/training/gold-labels/${encodeURIComponent(labelId)}/repair-spans`,
    { method: "POST" },
  );
}

export interface GroupedSurfaceForm {
  normalized: string;
  form: string;
  source?: string;
  status?: string;
  reviewer?: string;
  reviewed_at?: string;
  effective_at?: string;
  created_by?: string;
  created_at?: string;
  confidence?: number;
}

export interface ConceptGroup {
  concept_id: string;
  concept_fsn: string;
  semantic_tag?: string;
  read_code?: string;
  icd10?: string;
  icd10_term?: string;
  opcs4?: string;
  opcs4_term?: string;
  surface_forms: GroupedSurfaceForm[];
}

export interface ConceptGroupsPage {
  items: ConceptGroup[];
  total: number;
  offset: number;
  limit: number;
}

export async function fetchGroupedSurfaceForms(
  q?: string,
  limit = 50,
  offset = 0,
): Promise<ConceptGroupsPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (q) params.set("q", q);
  return fetchJson<ConceptGroupsPage>(`${API_BASE}/api/terminology/surface-forms/grouped?${params}`);
}

export async function keepSurfaceFormMapping(normalized: string, conceptId: string) {
  const params = new URLSearchParams({ keep_concept_id: conceptId });
  return fetchJson<{ normalized: string; kept_concept_id: string; removed: number }>(
    `${API_BASE}/api/terminology/surface-forms/${encodeURIComponent(normalized)}?${params}`,
    { method: "DELETE" },
  );
}

export async function suggestAliases(conceptId: string): Promise<string[]> {
  const result = await fetchJson<{ suggestions: string[]; concept_id: string }>(
    `${API_BASE}/api/terminology/concepts/${encodeURIComponent(conceptId)}/suggest-aliases`,
    { method: "POST" },
  );
  return result.suggestions;
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
  >(`${API_BASE}/api/terminology/concepts/${conceptId}/descendants?${params}`);
}

export interface AskLeoResult {
  concept_term: string | null;
  confidence: number;
  rationale: string;
  model_tier: string;
  resolved: boolean;
}

export async function askLeoRank(
  entityText: string,
  encounterText: string,
  candidates: Array<{ snomed_concept_id: string; term: string }>,
  tier: "small" | "big" | "max" = "small",
): Promise<{ selected_index: number; reason: string }> {
  return fetchJson(`${API_BASE}/api/training/coding-review/ask-leo-rank`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      entity_text: entityText,
      encounter_text: encounterText,
      candidates,
      tier,
    }),
  });
}

export async function askLeoSmart(
  entityText: string,
  encounterText: string,
  initialCandidates: Array<Record<string, unknown>>,
  semanticTags: string[] = [],
  tier: "small" | "big" | "max" = "small",
  assertion = "present",
): Promise<import("@/lib/types").AskLeoSmartResult> {
  return fetchJson(
    `${API_BASE}/api/training/coding-review/ask-leo-smart`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        entity_text: entityText,
        encounter_text: encounterText,
        initial_candidates: initialCandidates,
        semantic_tags: semanticTags,
        tier,
        assertion,
      }),
    },
  );
}

export async function createSuppressRule(
  matchText: string,
  matchLabel?: string,
  notes?: string,
): Promise<{ rule_id: string }> {
  return fetchJson<{ rule_id: string }>(
    `${API_BASE}/api/training/post-processor-rules`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "suppress",
        match_text: matchText,
        match_label: matchLabel ?? null,
        notes: notes ?? `Suppressed from gold label editor`,
        created_by: "operations_ui",
      }),
    },
  );
}

/** Escape a plain string for use as a literal regex pattern. */
function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Create a suppress rule that matches ALL entities extracted from any encounter
 * whose text contains a distinctive substring of the given encounter text.
 * Uses context_regex (no match_text) so every entity in a matching encounter
 * is suppressed in the post-processing step.
 */
export async function createEncounterSuppressRule(
  encounterText: string,
  notes?: string,
): Promise<{ rule_id: string }> {
  const snippet = encounterText.trim().slice(0, 80);
  const contextRegex = escapeRegex(snippet);
  return fetchJson<{ rule_id: string }>(
    `${API_BASE}/api/training/post-processor-rules`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "suppress",
        match_text: null,
        match_label: null,
        context_regex: contextRegex,
        window_chars: 500,
        notes: notes ?? `Encounter text suppressed from pipeline`,
        created_by: "operations_ui",
      }),
    },
  );
}

export async function askLeo(
  entityText: string,
  entityLabel: string,
  tier: "small" | "big" | "max" = "small",
  encounterText = "",
): Promise<AskLeoResult> {
  return fetchJson<AskLeoResult>(`${API_BASE}/api/training/coding-review/ask-leo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      entity_text: entityText,
      entity_label: entityLabel,
      tier,
      encounter_text: encounterText,
    }),
  });
}

export interface LabelDistributionRow {
  label: string;
  count: number;
}

export interface LabelDistribution {
  total_records: number;
  total_entities: number;
  distribution: LabelDistributionRow[];
}

export async function fetchLabelDistribution(): Promise<LabelDistribution> {
  return fetchJson<LabelDistribution>(
    `${API_BASE}/api/training/gold-labels/label-distribution`,
  );
}

export interface ExportDiagnosticItem {
  label_id: string;
  source: string;
  /** Full sentence text of the parent GoldLabel record. */
  text: string;
  /** Surface text of the entity that was dropped. */
  entity_text: string;
  /** Semantic label type e.g. DISORDER, FINDING. */
  label: string;
  /** Assertion value on the entity e.g. negated, hypothetical. */
  assertion?: string;
  reason: "assertion_filtered" | "span_misaligned";
}

export interface ExportDiagnostics {
  total_records: number;
  total_entities: number;
  excluded_assertions: string[];
  assertion_filtered: ExportDiagnosticItem[];
  span_misaligned: ExportDiagnosticItem[];
  summary: { assertion_filtered_count: number; span_misaligned_count: number };
}

export async function fetchExportDiagnostics(): Promise<ExportDiagnostics> {
  return fetchJson<ExportDiagnostics>(
    `${API_BASE}/api/training/gold-labels/export-diagnostics`,
  );
}

export interface PhraseSignatureCount {
  label: string;
  assertion: string;
  count: number;
}

export interface PhraseConflictExample {
  label_id: string;
  source: string;
  label: string;
  assertion: string;
  sentence_preview: string;
}

export interface PhraseConflictItem {
  phrase: string;
  occurrences: number;
  distinct_labels: number;
  distinct_assertions: number;
  primary_label?: string;
  outlier_count?: number;
  outlier_examples?: PhraseConflictExample[];
  signature_counts: PhraseSignatureCount[];
  examples: PhraseConflictExample[];
}

export interface PhraseConsistencyResponse {
  summary: {
    total_records: number;
    total_entities: number;
    unique_phrases: number;
    conflicting_phrases: number;
    assertion_only_variants?: number;
    approved_multilabel_variants?: number;
    min_occurrences: number;
  };
  conflicts: PhraseConflictItem[];
  approved_multilabel?: PhraseConflictItem[];
  policy?: PhraseMultiLabelApproval[];
}

export async function fetchPhraseConsistency(
  options?: { phrase?: string; minOccurrences?: number; top?: number },
): Promise<PhraseConsistencyResponse> {
  const params = new URLSearchParams();
  if (options?.phrase?.trim()) {
    params.set("phrase", options.phrase.trim());
  }
  if (options?.minOccurrences) {
    params.set("min_occurrences", String(options.minOccurrences));
  }
  if (options?.top) {
    params.set("top", String(options.top));
  }
  const qs = params.toString();
  return fetchJson<PhraseConsistencyResponse>(
    `${API_BASE}/api/training/gold-labels/phrase-consistency${qs ? `?${qs}` : ""}`,
  );
}

export interface PhraseMultiLabelApproval {
  phrase_norm: string;
  phrase_display: string;
  allowed_labels: string[];
  created_at?: string;
  created_by?: string;
  updated_at?: string;
  updated_by?: string;
}

export async function upsertPhraseMultiLabelApproval(payload: {
  phrase: string;
  allowed_labels: string[];
}): Promise<PhraseMultiLabelApproval> {
  return fetchJson<PhraseMultiLabelApproval>(
    `${API_BASE}/api/training/gold-labels/phrase-multilabel-approvals`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}
