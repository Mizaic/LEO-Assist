/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { api } from './client';

const ENDPOINT = '/benchmarks';

export interface BenchmarkSet {
  id: string;
  name: string;
  source: string;
  audit_year?: number;
  effective_from?: string;
  effective_to?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface BenchmarkValue {
  id?: string;
  metric_id: string;
  scope_type: string;
  scope_id: string;
  scope_name: string;
  value: number | null;
  unit: string;
  label: string;
  category: string;
  /** For composite metrics (e.g. sex: male/female), holds { male, female } percentages. */
  value_json?: Record<string, number> | null;
}

export interface BenchmarkScope {
  scope_id: string;
  scope_type: string;
  scope_name: string;
}

export interface BenchmarkPoint {
  metric_id: string;
  label: string;
  scope_type: string;
  scope_name: string;
  value: number | null;
  unit: string | null;
  source?: string | null;
  /** For composite metrics (e.g. sex: male/female), holds { male, female } percentages. */
  value_breakdown?: Record<string, number> | null;
}

export interface BenchmarkRule {
  id: string;
  name: string;
  query_definition: Record<string, unknown>;
  scope: string;
  output_metric_id: string;
  benchmark_set_id: string;
  last_run_at?: string | null;
  last_run_status?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface UploadBenchmarksParams {
  rawJson: Record<string, unknown>;
  templateId?: string;
  mapping?: Record<string, unknown>;
  auditId?: string;
  name?: string;
}

export async function getBenchmarkSets(params?: {
  source?: string;
  _count?: number;
  _offset?: number;
}): Promise<BenchmarkSet[]> {
  const searchParams = new URLSearchParams();
  if (params?.source) searchParams.set('source', params.source);
  if (params?._count) searchParams.set('_count', params._count.toString());
  if (params?._offset) searchParams.set('_offset', params._offset.toString());
  const query = searchParams.toString();
  const url = query ? `${ENDPOINT}/sets?${query}` : `${ENDPOINT}/sets`;
  return api.get<BenchmarkSet[]>(url);
}

export async function getBenchmarkSet(id: string): Promise<BenchmarkSet> {
  return api.get<BenchmarkSet>(`${ENDPOINT}/sets/${id}`);
}

export async function createBenchmarkSet(data: Partial<BenchmarkSet>): Promise<BenchmarkSet> {
  return api.post<BenchmarkSet>(`${ENDPOINT}/sets`, data);
}

export async function deleteBenchmarkSet(id: string): Promise<void> {
  return api.delete<void>(`${ENDPOINT}/sets/${id}`);
}

export async function getBenchmarkCategories(setId: string): Promise<string[]> {
  return api.get<string[]>(`${ENDPOINT}/sets/${setId}/categories`);
}

export async function getBenchmarkScopes(setId: string): Promise<BenchmarkScope[]> {
  return api.get<BenchmarkScope[]>(`${ENDPOINT}/sets/${setId}/scopes`);
}

export async function getBenchmarkValues(
  setId: string,
  params?: { metric_id?: string; scope_type?: string; scope_id?: string; category?: string }
): Promise<BenchmarkValue[]> {
  const searchParams = new URLSearchParams();
  if (params?.metric_id) searchParams.set('metric_id', params.metric_id);
  if (params?.scope_type) searchParams.set('scope_type', params.scope_type);
  if (params?.scope_id) searchParams.set('scope_id', params.scope_id);
  if (params?.category) searchParams.set('category', params.category);
  const query = searchParams.toString();
  const url = query ? `${ENDPOINT}/sets/${setId}/values?${query}` : `${ENDPOINT}/sets/${setId}/values`;
  return api.get<BenchmarkValue[]>(url);
}

export async function updateBenchmarkValue(
  setId: string,
  valueId: string,
  value: number
): Promise<BenchmarkValue> {
  return api.put<BenchmarkValue>(`${ENDPOINT}/sets/${setId}/values/${valueId}`, { value });
}

export async function deleteBenchmarkValue(setId: string, valueId: string): Promise<void> {
  return api.delete<void>(`${ENDPOINT}/sets/${setId}/values/${valueId}`);
}

export async function getBenchmarkComparison(
  setId: string,
  metricId: string
): Promise<BenchmarkPoint[]> {
  return api.get<BenchmarkPoint[]>(`${ENDPOINT}/sets/${setId}/comparison/${metricId}`);
}

export async function uploadBenchmarks(params: UploadBenchmarksParams): Promise<{
  audit_id: string;
  count: number;
  status: string;
}> {
  return api.post<{ audit_id: string; count: number; status: string }>(
    `${ENDPOINT}/upload`,
    params
  );
}

export async function inferBenchmarkStructure(rawJson: Record<string, unknown>): Promise<{
  keys: string[];
  sample: Record<string, unknown>;
  depth: number;
}> {
  return api.post<{ keys: string[]; sample: Record<string, unknown>; depth: number }>(
    `${ENDPOINT}/infer-structure`,
    { rawJson }
  );
}

export async function getBenchmarkRules(params?: {
  _count?: number;
  _offset?: number;
}): Promise<BenchmarkRule[]> {
  const searchParams = new URLSearchParams();
  if (params?._count) searchParams.set('_count', params._count.toString());
  if (params?._offset) searchParams.set('_offset', params._offset.toString());
  const query = searchParams.toString();
  const url = query ? `${ENDPOINT}/rules?${query}` : `${ENDPOINT}/rules`;
  return api.get<BenchmarkRule[]>(url);
}

export async function getBenchmarkRule(id: string): Promise<BenchmarkRule> {
  return api.get<BenchmarkRule>(`${ENDPOINT}/rules/${id}`);
}

export async function createBenchmarkRule(data: Partial<BenchmarkRule>): Promise<BenchmarkRule> {
  return api.post<BenchmarkRule>(`${ENDPOINT}/rules`, data);
}

export async function updateBenchmarkRule(
  id: string,
  data: Partial<BenchmarkRule>
): Promise<BenchmarkRule> {
  return api.put<BenchmarkRule>(`${ENDPOINT}/rules/${id}`, data);
}

export async function deleteBenchmarkRule(id: string): Promise<void> {
  return api.delete<void>(`${ENDPOINT}/rules/${id}`);
}

export async function runBenchmarkRule(
  ruleId: string,
  params?: { org_id?: string; org_ods_code?: string; scope_type?: string }
): Promise<{ status: string; count?: number; error?: string }> {
  const searchParams = new URLSearchParams();
  if (params?.org_id) searchParams.set('org_id', params.org_id);
  if (params?.org_ods_code) searchParams.set('org_ods_code', params.org_ods_code);
  if (params?.scope_type) searchParams.set('scope_type', params.scope_type);
  const query = searchParams.toString();
  const url = query ? `${ENDPOINT}/rules/${ruleId}/run?${query}` : `${ENDPOINT}/rules/${ruleId}/run`;
  return api.post<{ status: string; count?: number; error?: string }>(url, undefined);
}
