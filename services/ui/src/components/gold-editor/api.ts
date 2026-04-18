/**
 * Thin shared API helpers for the GoldLabelEditorDialog (DI-LEO-AI-219).
 *
 * Routes:
 *   - patchGoldLabelEntities    -> existing PATCH on the gold label.
 *   - createGoldLabelFromDryRun -> Evaluate-stage seed (DI-LEO-AI-222).
 *   - createGoldLabelFromEncounter -> /care surfaces seed (DI-LEO-AI-220).
 *   - syncCodedLinksFromGold    -> /care surfaces dual save (DI-LEO-AI-221).
 */
import type { GoldLabel, SavedGoldEntity } from "./types";

const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) || "";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    let message = `${res.status}`;
    try {
      const payload = (await res.json()) as { detail?: unknown; message?: string };
      if (typeof payload.message === "string" && payload.message.trim()) {
        message = payload.message.trim();
      } else if (typeof payload.detail === "string" && payload.detail.trim()) {
        message = payload.detail.trim();
      }
    } catch {
      // keep status-only message
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export async function patchGoldLabelEntities(
  labelId: string,
  entities: SavedGoldEntity[],
): Promise<{ label_id: string; entities: SavedGoldEntity[] }> {
  return fetchJson(
    `${API_BASE}/api/training/gold-labels/${encodeURIComponent(labelId)}/entities`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entities }),
    },
  );
}

export interface DryRunGoldLabelResponse {
  candidate_id: string;
  label_id: string;
  source: string;
  entity_count: number;
  dropped_entity_count: number;
  gold_label: GoldLabel;
}

export async function createGoldLabelFromDryRun(payload: {
  encounter_text: string;
  entities: Array<Record<string, unknown>>;
  evaluation_id?: string | null;
  source_run_id?: string | null;
  source_model_version?: string | null;
}): Promise<DryRunGoldLabelResponse> {
  return fetchJson(`${API_BASE}/api/training/candidates/from-dry-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export interface EncounterGoldLabelResponse {
  candidate_id: string;
  label_id: string;
  source: string;
  patient_id: string;
  encounter_id: string;
  source_coded_links_count: number;
  entity_count: number;
  dropped_link_count: number;
  baseline_concept_ids: string[];
  gold_label: GoldLabel;
}

export async function createGoldLabelFromEncounter(payload: {
  patient_id: string;
  encounter_id: string;
}): Promise<EncounterGoldLabelResponse> {
  return fetchJson(`${API_BASE}/api/training/gold-labels/from-encounter`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export interface SyncCodedLinksResponse {
  gold_label_id: string;
  live_links_added: number;
  live_links_removed: number;
  live_links_updated: number;
  baseline_concept_ids: string[];
}

export async function syncCodedLinksFromGold(payload: {
  patient_id: string;
  encounter_id: string;
  label_id: string;
  expected_baseline_concept_ids: string[];
  entities: SavedGoldEntity[];
}): Promise<SyncCodedLinksResponse> {
  const { patient_id, encounter_id, ...body } = payload;
  return fetchJson(
    `${API_BASE}/api/patients/${encodeURIComponent(
      patient_id,
    )}/encounters/${encodeURIComponent(encounter_id)}/coded-links/sync-from-gold`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}
