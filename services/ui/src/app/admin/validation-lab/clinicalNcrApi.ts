/**
 * Validation Lab product NCR client.
 *
 * Atlas: DI-287FFFD0
 */
import { formatLabApiError } from "./labApi";
import { filterProductNcrs, type NcrDraft, type ProductNcr } from "./ncrDraft";
import { triggerReauth } from "@/lib/api/client";

export async function listProductNcrs(query = ""): Promise<ProductNcr[]> {
  const q = query.trim();
  const url = q
    ? `/api/validation-lab/ncrs?q=${encodeURIComponent(q)}`
    : "/api/validation-lab/ncrs";
  const body = await apiJson<{ items?: ProductNcr[] }>(url);
  return filterProductNcrs(body.items || [], "");
}

export function getProductNcr(ncId: string): Promise<ProductNcr> {
  return apiJson(`/api/validation-lab/ncrs/${encodeURIComponent(ncId)}`);
}

export function createProductNcr(
  draft: NcrDraft,
  extra?: { runId?: string; why?: string },
): Promise<ProductNcr> {
  return apiJson("/api/validation-lab/ncrs", {
    method: "POST",
    body: JSON.stringify({
      title: draft.title,
      description: draft.description,
      severity: draft.severity,
      run_id: extra?.runId || "",
      why: extra?.why || "",
    }),
  });
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) await triggerReauth();
    throw new Error(formatLabApiError(body, res.status));
  }
  return body as T;
}
