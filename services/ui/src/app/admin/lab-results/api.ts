import type {
  LabInterpretation,
  LabReferenceRange,
  LabResultConfig,
  LabResultConfigSummary,
  LabUnitConversion,
} from "./types";

async function parseApiError(res: Response): Promise<string> {
  const text = await res.text();
  if (text.trimStart().startsWith("<!")) {
    return `Unable to load lab result config (${res.status}). Please retry.`;
  }
  return text || `Request failed (${res.status})`;
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function listLabResultConfigs(q = "") {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  params.set("limit", "200");
  return apiJson<{ items: LabResultConfigSummary[] }>(
    `/api/lab-result-configs?${params.toString()}`,
  );
}

export async function getLabResultConfig(conceptId: string) {
  return apiJson<{ item: LabResultConfig }>(
    `/api/lab-result-configs/${encodeURIComponent(conceptId)}`,
  );
}

export async function saveLabResultConfig(
  conceptId: string,
  body: { display_name: string; canonical_unit: string; source?: string },
) {
  return apiJson(`/api/lab-result-configs/${encodeURIComponent(conceptId)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function saveUnitConversion(
  conceptId: string,
  body: LabUnitConversion,
) {
  return apiJson(
    `/api/lab-result-configs/${encodeURIComponent(conceptId)}/conversions`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function saveReferenceRange(
  conceptId: string,
  body: Partial<LabReferenceRange>,
) {
  return apiJson(`/api/lab-result-configs/${encodeURIComponent(conceptId)}/ranges`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function saveInterpretation(
  conceptId: string,
  body: { classification: string; finding_concept_id: string },
) {
  return apiJson(
    `/api/lab-result-configs/${encodeURIComponent(conceptId)}/interpretations`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export type { LabInterpretation, LabReferenceRange, LabResultConfigSummary };
