import { api } from './client';
import type { Measure, Bundle } from '@/lib/types/fhir';
import type { CohortFilters } from '@/lib/types/layout';

const ENDPOINT = '/fhir/Measure';

export interface MeasureSearchParams {
  name?: string;
  status?: string;
  topic?: string;
  _count?: number;
  _offset?: number;
}

export async function getMeasures(
  params?: MeasureSearchParams
): Promise<Bundle<Measure>> {
  const searchParams = new URLSearchParams();
  if (params?.name) searchParams.set('name', params.name);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.topic) searchParams.set('topic', params.topic);
  if (params?._count) searchParams.set('_count', params._count.toString());
  if (params?._offset) searchParams.set('_offset', params._offset.toString());

  const query = searchParams.toString();
  const url = query ? `${ENDPOINT}?${query}` : ENDPOINT;
  return api.get<Bundle<Measure>>(url);
}

export async function getMeasure(id: string): Promise<Measure> {
  return api.get<Measure>(`${ENDPOINT}/${id}`);
}

export async function createMeasure(
  measure: Omit<Measure, 'id'>
): Promise<Measure> {
  const id = crypto.randomUUID();
  const measureWithId = { ...measure, id };
  return api.put<Measure>(`${ENDPOINT}/${id}`, measureWithId);
}

export async function updateMeasure(
  id: string,
  measure: Measure
): Promise<Measure> {
  return api.put<Measure>(`${ENDPOINT}/${id}`, measure);
}

export async function deleteMeasure(id: string): Promise<void> {
  return api.delete<void>(`${ENDPOINT}/${id}`);
}

export async function evaluateMeasure(
  id: string,
  params: {
    periodStart: string;
    periodEnd: string;
    subject?: string;
    orgId?: string;
    orgIds?: string[];
    cohortFilters?: CohortFilters;
  }
): Promise<unknown> {
  const searchParams = new URLSearchParams({
    periodStart: params.periodStart,
    periodEnd: params.periodEnd,
  });
  if (params.subject) searchParams.set('subject', params.subject);
  if (params.orgId) searchParams.set('org_id', params.orgId);
  if (params.orgIds?.length) {
    params.orgIds.forEach((v) => searchParams.append('org_ids', v));
  }

  if (params.cohortFilters) {
    const arrayKeys = new Set(['ce_status', 'ce_status_exclude', 'ce_condition_type']);
    Object.entries(params.cohortFilters).forEach(([key, value]) => {
      if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) return;
      if (arrayKeys.has(key) && Array.isArray(value)) {
        const filtered = value.map((entry) => String(entry).trim()).filter(Boolean);
        if (filtered.length > 0) searchParams.set(key, filtered.join(','));
        return;
      }
      searchParams.set(key, String(value));
    });
  }

  return api.get(`${ENDPOINT}/${id}/$evaluate-measure?${searchParams.toString()}`);
}

export type CohortVariant = 'diagnosed' | 'referred_excluded' | 'all_referred';

export type AggregationType = 'count' | 'median' | 'percentage';

export interface QueryDefinition {
  nodeLabel: string;
  filters?: Array<{ property: string; op: string; value: unknown }>;
  groupBy?: string | null;
  scopeType: string;
  cohortVariant?: CohortVariant;
  aggregation?: AggregationType;
  valueProperty?: string;
  percentageProperty?: string;
  percentageValue?: boolean;
  name?: string;
}

export interface GenerateMeasureResponse {
  libraryId: string;
  cypher: string;
}

export async function generateMeasureQuery(
  definition: QueryDefinition
): Promise<GenerateMeasureResponse> {
  return api.post<GenerateMeasureResponse>(`${ENDPOINT}/$generate`, definition);
}

export interface PreviewMeasureResponse {
  rows: Array<Record<string, unknown>>;
}

export async function previewMeasureQuery(
  definition: QueryDefinition,
  orgId: string
): Promise<PreviewMeasureResponse> {
  return api.post<PreviewMeasureResponse>(
    `${ENDPOINT}/$preview?org_id=${encodeURIComponent(orgId)}`,
    definition
  );
}
