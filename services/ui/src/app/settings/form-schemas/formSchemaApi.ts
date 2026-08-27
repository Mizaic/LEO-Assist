/**
 * API helpers for the form template library settings page.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */

export interface SchemaSummary {
  schema_id: string;
  fingerprint: string;
  form_name: string;
  status: string;
  created_at: string;
  updated_at: string;
  organization_id: string;
  service_id: string;
}

export async function fetchFormSchemas(): Promise<SchemaSummary[]> {
  const res = await fetch("/api/form-schemas", {
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) throw new Error("Could not load form templates. Please retry.");
  const data = await res.json();
  return data.schemas ?? [];
}

export async function deleteFormSchema(fingerprint: string): Promise<void> {
  const res = await fetch(`/api/form-schemas/${encodeURIComponent(fingerprint)}`, {
    method: "DELETE",
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) {
    const detail = await readErrorDetail(res);
    throw new Error(detail || "Could not delete this form template. Try again.");
  }
}

async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
  } catch {
    /* ignore */
  }
  return "";
}

export function formatSchemaDate(raw: string): string {
  if (!raw) return "Not saved yet";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
