/**
 * Thin shared API helpers for the GoldLabelEditorDialog (DI-LEO-AI-219).
 *
 * Routes:
 *   - patchGoldLabelEntities    -> existing PATCH on the gold label.
 *   - createGoldLabelFromDryRun -> Evaluate-stage seed (DI-LEO-AI-222).
 *   - createGoldLabelFromEncounter -> /care surfaces seed (DI-LEO-AI-220).
 *   - syncCodedLinksFromGold    -> /care surfaces dual save (DI-LEO-AI-221).
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
import type { GoldLabel, SavedGoldEntity } from "./types";

// All requests are issued from "use client" components in the browser
// and must hit the Next.js proxy at the same origin (port 3000 in
// local dev, the Container App ingress in cloud). The proxy in
// services/ui/src/proxy.ts strips the /api/ prefix and forwards to
// the Core API. Prepending NEXT_PUBLIC_API_BASE here would bypass the
// proxy and 404 against the Core API (which does not mount routes
// under /api/), so we deliberately keep these paths origin-relative.

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
    `/api/training/gold-labels/${encodeURIComponent(labelId)}/entities`,
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
  return fetchJson(`/api/training/candidates/from-dry-run`, {
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
  return fetchJson(`/api/training/gold-labels/from-encounter`, {
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
    `/api/patients/${encodeURIComponent(
      patient_id,
    )}/encounters/${encodeURIComponent(encounter_id)}/coded-links/sync-from-gold`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}
