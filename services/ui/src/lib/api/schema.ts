/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { api } from './client';

const SCHEMA_ENDPOINT = '/fhir/schema/patient-graph';

export interface AggregationTarget {
  nodeLabel: string;
  description: string;
}

export interface FilterDef {
  property: string;
  type: string;
  fhirType?: string;
  exampleValues?: string[];
  /** When true, fetch distinct values from Neo4j for select/multi-select */
  distinctFromNeo4j?: boolean;
}

export interface ScopeTypeDef {
  scopeType: string;
  paramName: string;
  label: string;
}

export interface PatientGraphSchema {
  aggregationTargets: AggregationTarget[];
  filters: Record<string, FilterDef[]>;
  groupBy: Record<string, string[]>;
  scopeTypes: ScopeTypeDef[];
  valueProperties?: Record<string, string[]>;
}

export async function getPatientGraphSchema(): Promise<PatientGraphSchema> {
  return api.get<PatientGraphSchema>(SCHEMA_ENDPOINT);
}

export async function getDistinctFilterValues(
  nodeLabel: string,
  property: string
): Promise<string[]> {
  const params = new URLSearchParams({ node_label: nodeLabel, property_name: property });
  return api.get<string[]>(`/fhir/schema/distinct-values?${params}`);
}
