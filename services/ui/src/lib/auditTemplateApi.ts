/**
 * API client for the audit template and metric endpoints.
 *
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-64CA7740, DI-758B73A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A9863AB6")
 */

import { triggerReauth } from "@/lib/api/client";

function resolveApiBase(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return (process.env.INTERNAL_API_BASE || "http://localhost:8000").replace(
    /\/+$/,
    ""
  );
}

const ANALYTICS_BASE = `${resolveApiBase()}/api/proxy/analytics`;

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    if (res.status === 401) await triggerReauth();
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ||
        `Request failed (${res.status})`
    );
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TileType =
  | "bar_chart"
  | "line_chart"
  | "kpi_strip"
  | "table"
  | "interval_plot"
  | "text"
  | "widget";

export interface TileLayout {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface TileAnnotation {
  type: "callout" | "threshold";
  label: string;
  value?: number;
  target_key?: string;
}

export interface TileStoryConfig {
  headline?: string;
  highlight_key?: string;
  annotations?: TileAnnotation[];
  animate_in?: boolean;
}

export interface AuditTile {
  tile_id: string;
  label: string;
  tile_type: TileType;
  metric_id: string;
  param_overrides: Record<string, unknown>;
  section?: string;
  layout: TileLayout;
  story?: TileStoryConfig;
}

export type AuditTemplateStatus = "draft" | "published" | "archived";

export interface AuditTemplate {
  template_id: string;
  title: string;
  version: number;
  status: AuditTemplateStatus;
  tiles: AuditTile[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface TemplateAssignment {
  assignment_id: string;
  template_id: string;
  version: number;
  scope_type: "org" | "group";
  scope_id: string;
  published_at: string;
  published_by: string;
}

// ---------------------------------------------------------------------------
// Metric catalogue types
// ---------------------------------------------------------------------------

export interface MetricParamSpec {
  type: string;
  format?: string;
  required?: boolean;
  default?: unknown;
  enum?: string[];
  minimum?: number;
  maximum?: number;
}

export interface MetricOutputColumn {
  name: string;
  type: string;
}

export interface MetricCatalogueEntry {
  metric_id: string;
  title: string;
  description: string;
  output_type: string;
  param_schema: Record<string, MetricParamSpec>;
  output_schema: MetricOutputColumn[];
  compatible_tile_types: TileType[];
}

export interface MetricRunResult {
  metric_id: string;
  columns: string[];
  rows: unknown[][];
}

// ---------------------------------------------------------------------------
// Widget catalogue (pre-built specialised components)
// ---------------------------------------------------------------------------

export interface WidgetCatalogueEntry {
  widget_id: string;
  title: string;
  description: string;
  /** Broad grouping shown in the picker. */
  category: string;
}

/**
 * Specialised widgets that render full NCDA audit components rather than
 * calling the metric /run endpoint. Each widget_id maps to a concrete React
 * component inside WidgetTile.tsx.
 */
export const WIDGET_CATALOGUE: WidgetCatalogueEntry[] = [
  {
    widget_id: "symptoms_ppv",
    title: "Symptoms at Referral",
    description:
      "Per-symptom positive predictive value heatmaps. Shows how often each symptom led to a confirmed cancer diagnosis.",
    category: "Clinical signals",
  },
  {
    widget_id: "blood_signal",
    title: "Blood Result Cancer Signal",
    description:
      "GDS blood test distribution and signal analysis. Requires the GDS enrichment pipeline to be active.",
    category: "Clinical signals",
  },
];

// ---------------------------------------------------------------------------
// Request payloads
// ---------------------------------------------------------------------------

export interface CreateTemplatePayload {
  title: string;
  tiles: Omit<AuditTile, "tile_id">[];
}

export interface UpdateTemplatePayload {
  title?: string;
  tiles?: Omit<AuditTile, "tile_id">[];
}

export interface PublishTemplatePayload {
  template_id: string;
  scope_type: "org" | "group" | "global";
  scope_id: string;
}

// ---------------------------------------------------------------------------
// Metric endpoints
// ---------------------------------------------------------------------------

/** Return the metric catalogue (no Cypher exposed). */
export async function fetchMetricCatalogue(): Promise<MetricCatalogueEntry[]> {
  return fetchJson<MetricCatalogueEntry[]>(`${ANALYTICS_BASE}/audit-metrics`);
}

/** Execute a metric with caller-supplied params.
 *
 * @param previewOrgId - Admin-only: scope to a specific org for template preview.
 */
export async function runMetric(
  metricId: string,
  params: Record<string, unknown> = {},
  previewOrgId?: string,
): Promise<MetricRunResult> {
  return fetchJson<MetricRunResult>(
    `${ANALYTICS_BASE}/audit-metrics/${encodeURIComponent(metricId)}/run`,
    {
      method: "POST",
      body: JSON.stringify({
        params,
        ...(previewOrgId ? { preview_org_id: previewOrgId } : {}),
      }),
    }
  );
}

// ---------------------------------------------------------------------------
// Template CRUD (admin)
// ---------------------------------------------------------------------------

/** Fetch a single template by ID. Returns null if not found. Admin only. */
export async function fetchTemplate(
  templateId: string
): Promise<AuditTemplate | null> {
  try {
    return await fetchJson<AuditTemplate>(
      `${ANALYTICS_BASE}/audit-templates/${encodeURIComponent(templateId)}`
    );
  } catch (e) {
    if (e instanceof Error && e.message.includes("404")) return null;
    throw e;
  }
}

/** List all non-archived templates. Admin only. */
export async function listTemplates(): Promise<AuditTemplate[]> {
  return fetchJson<AuditTemplate[]>(`${ANALYTICS_BASE}/audit-templates`);
}

/** Create a new draft template. Admin only. */
export async function createTemplate(
  payload: CreateTemplatePayload
): Promise<AuditTemplate> {
  return fetchJson<AuditTemplate>(`${ANALYTICS_BASE}/audit-templates`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Update a template's title and/or tiles. Admin only. */
export async function updateTemplate(
  templateId: string,
  payload: UpdateTemplatePayload
): Promise<AuditTemplate> {
  return fetchJson<AuditTemplate>(
    `${ANALYTICS_BASE}/audit-templates/${encodeURIComponent(templateId)}`,
    { method: "PATCH", body: JSON.stringify(payload) }
  );
}

/** Archive a template. Admin only. */
export async function archiveTemplate(templateId: string): Promise<void> {
  return fetchJson<void>(
    `${ANALYTICS_BASE}/audit-templates/${encodeURIComponent(templateId)}`,
    { method: "DELETE" }
  );
}

// ---------------------------------------------------------------------------
// Publish
// ---------------------------------------------------------------------------

/** Publish a template to an org or group. Admin only. */
export async function publishTemplate(
  templateId: string,
  payload: PublishTemplatePayload
): Promise<TemplateAssignment> {
  return fetchJson<TemplateAssignment>(
    `${ANALYTICS_BASE}/audit-templates/${encodeURIComponent(templateId)}/publish`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

// ---------------------------------------------------------------------------
// Active template (any authenticated user)
// ---------------------------------------------------------------------------

/** Return the template published to the caller's org. Null if none found. */
export async function fetchActiveTemplate(): Promise<AuditTemplate | null> {
  return fetchJson<AuditTemplate | null>(
    `${ANALYTICS_BASE}/audit-templates/active`
  );
}
