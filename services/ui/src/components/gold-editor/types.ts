/**
 * Shared types for the GoldLabelEditorDialog (DI-LEO-AI-208).
 *
 * Re-exports the canonical GoldLabel + Entity shapes so consumers
 * (Evaluate stage, /care/patients, /care/encounters, candidates tab)
 * import from one place.
 */
export type {
  Entity,
  EntityRelation,
  GoldLabel,
  RejectedRelation,
  Candidate,
  CandidateStats,
  GoldStats,
  SimilarCandidateItem,
} from "@/components/gold-dataset/goldDatasetTypes";

export type {
  SavedGoldEntity,
  GoldDialogSaveMode,
  GoldDialogEntitySaver,
} from "@/components/gold-dataset/GoldDatasetPanel";

/**
 * Live-encounter context required by dual-save consumers.
 *
 * Hosts (e.g. EncounterCard, EncounterMissionControl) MUST pass these
 * into the dialog wrapper alongside the GoldLabel that came back from
 * `POST /training/gold-labels/from-encounter` so the sync-from-gold
 * call can target the correct live encounter and detect optimistic
 * concurrency drift via baseline_concept_ids (R-LEO-AI-187).
 */
export interface DualSaveEncounterContext {
  patient_id: string;
  encounter_id: string;
  baseline_concept_ids: string[];
}
