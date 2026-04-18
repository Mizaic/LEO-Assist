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
  relation_changes?: string | null;
  source: string;
  status: string;
  uncertainty_score?: number | null;
  rarity_score?: number | null;
  priority_score?: number | null;
  rare_labels?: string[] | null;
  hitl_reason?: string | null;
  hitl_guidance?: string | null;
  created_at: string;
  updated_at: string;
  // -- AI first-pass audit fields (DI-LEO-AI-208 / DI-LEO-AI-209) --
  // Set when an AI first-pass run has overwritten this candidate's
  // entities_json. The original snapshot is preserved write-once
  // in entities_json_original so reviewers can flip back to see
  // what the AI changed.
  ai_first_pass_run_id?: string | null;
  ai_first_pass_at?: string | null;
  entities_json_original?: string | null;
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

export interface RejectedRelation {
  /** Relation type e.g. "finding_site", "interprets". */
  type: string;
  /** Stable text-based identifier for the target entity. */
  target_text: string;
  reason: string;
}

export interface Entity {
  text: string;
  label?: string;
  semantic_tag?: string;
  snomed_concept_id?: string;
  snomed_term?: string;
  assertion?: string;
  body_site_concept_id?: string;
  body_site_term?: string;
  relations?: EntityRelation[];
  /** Relation suggestions the reviewer has explicitly dismissed. Persisted
   *  alongside entities so they do not reappear on reload. */
  rejected_relations?: RejectedRelation[];
}

export interface EntityRelation {
  type: string;
  target_idx: number;
  target_text?: string;
  confidence?: number;
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
