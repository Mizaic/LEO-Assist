export interface CandidateStats {
  total: number;
  pending: number;
  processing: number;
  completed: number;
  failed: number;
}

export interface GoldStats {
  total: number;
  avg_quality_score: number | null;
  high_quality: number;
}

export interface Candidate {
  candidate_id: string;
  text: string;
  entities_json?: string | null;
  source: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface GoldLabel {
  label_id: string;
  text: string;
  entities_json: string | null;
  quality_score: number | null;
  source: string;
  verified_by: string | null;
  verified_at: string | null;
  candidate_id: string | null;
  updated_at: string;
}

export interface Entity {
  text: string;
  label?: string;
  semantic_tag?: string;
  snomed_concept_id?: string;
  snomed_term?: string;
  assertion?: string;
}

export interface SimilarCandidateItem {
  candidate_id: string;
  text: string;
  source: string | null;
  status: string | null;
  updated_at: string | null;
  entities_json: string | null;
  similarity: number;
}
