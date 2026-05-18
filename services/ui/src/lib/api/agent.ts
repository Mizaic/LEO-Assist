/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { api } from './client';
import type { CohortFilters } from '@/lib/types/layout';
import type { MeasureReport } from '@/lib/types/fhir';

export type AgentModelSize = 'big' | 'small';
export type AgentItem = string | Record<string, unknown>;

export interface InterpretMeasuresRequest {
  report_id: string;
  measure_ids?: string[];
  measure_id?: string;
  measure_report?: MeasureReport;
  measure_reports?: Array<{
    measure_id: string;
    report: MeasureReport;
    title?: string;
    cohort_filters?: CohortFilters;
  }>;
  measure_title_overrides?: Record<string, string>;
  model_size?: AgentModelSize;
  user_goal?: string;
  organization_id?: string;
  cohort_filters?: CohortFilters;
}

export interface AgentInterpretation {
  summary: string;
  insights: AgentItem[];
  quality_checks: AgentItem[];
  recommended_measures: AgentItem[];
  follow_up_questions: AgentItem[];
  caveats: AgentItem[];
  model: {
    size: AgentModelSize;
    id: string;
  };
  generated_at: string;
}

export interface InterpretMeasuresResponse {
  reportId: string;
  interpretation: AgentInterpretation;
}

export interface ExecutiveSummaryRequest {
  report_id: string;
  summaries?: Record<string, unknown>[];
  excluded_measure_ids?: string[];
  mode?: 'default' | 'tight';
  model_size?: AgentModelSize;
}

export interface ExecutiveSummaryResponse {
  reportId: string;
  summary: string;
  mode: 'default' | 'tight';
  generated_at: string;
}

export async function interpretMeasures(
  payload: InterpretMeasuresRequest
): Promise<InterpretMeasuresResponse> {
  return api.post<InterpretMeasuresResponse>('/api/agent/interpret', payload);
}

export async function executiveSummary(
  payload: ExecutiveSummaryRequest
): Promise<ExecutiveSummaryResponse> {
  return api.post<ExecutiveSummaryResponse>('/api/agent/executive-summary', payload);
}
