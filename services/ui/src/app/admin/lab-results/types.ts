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
}

export interface LabResultConfig extends LabResultConfigSummary {
  conversions: LabUnitConversion[];
  ranges: LabReferenceRange[];
  interpretations: LabInterpretation[];
}
