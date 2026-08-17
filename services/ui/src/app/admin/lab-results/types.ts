/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
export interface LabUnitConversion {
  unit: string;
  factor: number;
  offset: number;
}

export interface LabReferenceRange {
  range_id: string;
  sex?: string | null;
  age_min?: number | null;
  age_max?: number | null;
  low?: number | null;
  high?: number | null;
  critical_low?: number | null;
  critical_high?: number | null;
  source?: string | null;
  org_id?: string | null;
}

export interface LabInterpretation {
  classification: string;
  concept_id: string;
  term?: string | null;
}

export interface LabResultConfigSummary {
  concept_id: string;
  display_name: string;
  canonical_unit: string;
  source?: string | null;
  updated_at?: string | null;
  conversion_count?: number;
  range_count?: number;
  interpretation_count?: number;
}

export interface LabResultConfig extends LabResultConfigSummary {
  conversions: LabUnitConversion[];
  ranges: LabReferenceRange[];
  interpretations: LabInterpretation[];
}
