/**
 * Phrase mappings API (inbox / drafts / review / publish).
 *
 * Atlas trace:
 *   DI: DI-D90542E5, DI-6BD7B681
 */
const BASE = "/api/training/phrase-mappings";

export interface UncodedPhrase {
  phrase_key: string;
  normalized: string;
  extracted_tag: string;
  last_extractor?: string;
  note_count: number;
  last_score: number | null;
  last_best_term: string;
  last_best_concept: string;
  last_best_tag: string;
  sample_span: string;
  sample_sentence: string;
  status: string;
  draft_action?: string;
  draft_concept_id?: string;
  draft_concept_term?: string;
  draft_reason?: string;
  draft_author?: string;
  last_seen_at?: string;
}

export interface PhraseMappingCounts {
  inbox: number;
  draft: number;
  review: number;
  closed: number;
  my_drafts: number;
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail || "Request failed. Please try again.");
  }
  return res.json() as Promise<T>;
}

function jsonHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
  };
}

export async function fetchPhraseCounts(): Promise<PhraseMappingCounts> {
  const res = await fetch(`${BASE}/counts`, {
    credentials: "include",
    headers: jsonHeaders(),
  });
  return readJson<PhraseMappingCounts>(res);
}

export async function fetchPhraseMappings(
  status: string,
  page = 1,
): Promise<{ items: UncodedPhrase[]; total: number }> {
  const params = new URLSearchParams({ status, page: String(page), page_size: "50" });
  const res = await fetch(`${BASE}?${params}`, {
    credentials: "include",
    headers: jsonHeaders(),
  });
  return readJson<{ items: UncodedPhrase[]; total: number }>(res);
}

export async function fetchPhraseItem(
  phrase_key: string,
): Promise<UncodedPhrase> {
  const params = new URLSearchParams({ phrase_key });
  const res = await fetch(`${BASE}/item?${params}`, {
    credentials: "include",
    headers: jsonHeaders(),
  });
  return readJson<UncodedPhrase>(res);
}

export async function ensurePhrase(body: {
  phrase_key: string;
  extracted_tag?: string;
  extracted_source?: string;
  sample_span?: string;
  sample_sentence?: string;
}): Promise<UncodedPhrase> {
  const res = await fetch(`${BASE}/ensure`, {
    method: "POST",
    credentials: "include",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  return readJson<UncodedPhrase>(res);
}

export async function submitPhrase(phrase_key: string): Promise<unknown> {
  const res = await fetch(`${BASE}/submit`, {
    method: "POST",
    credentials: "include",
    headers: jsonHeaders(),
    body: JSON.stringify({ phrase_key }),
  });
  return readJson(res);
}

export async function savePhraseDraft(body: {
  phrase_key: string;
  action: string;
  concept_id?: string;
  concept_term?: string;
  reason?: string;
}): Promise<{ phrase_key: string; status: string }> {
  const res = await fetch(`${BASE}/draft`, {
    method: "POST",
    credentials: "include",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function submitPhraseDrafts(): Promise<{ submitted: number }> {
  const res = await fetch(`${BASE}/submit`, {
    method: "POST",
    credentials: "include",
    headers: jsonHeaders(),
    body: JSON.stringify({}),
  });
  return readJson(res);
}

export async function sendBackPhrase(phrase_key: string): Promise<unknown> {
  const res = await fetch(`${BASE}/send-back`, {
    method: "POST",
    credentials: "include",
    headers: jsonHeaders(),
    body: JSON.stringify({ phrase_key }),
  });
  return readJson(res);
}

export async function publishPhrase(
  phrase_key: string,
  breakGlassReason = "",
): Promise<unknown> {
  const body: { phrase_key: string; break_glass_reason?: string } = {
    phrase_key,
  };
  const reason = breakGlassReason.trim();
  if (reason) body.break_glass_reason = reason;
  const res = await fetch(`${BASE}/publish`, {
    method: "POST",
    credentials: "include",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  return readJson(res);
}
