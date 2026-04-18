/**
 * Public surface for the shared gold-label editor (DI-LEO-AI-208).
 *
 * Consumers should import only from this barrel:
 *
 *   import {
 *     GoldLabelEditorDialog,
 *     useDualSaveAdapter,
 *     createGoldLabelFromEncounter,
 *     syncCodedLinksFromGold,
 *   } from "@/components/gold-editor";
 */
export { GoldLabelEditorDialog, default } from "./GoldLabelEditorDialog";
export { useDualSaveAdapter } from "./useDualSaveAdapter";
export type {
  Entity,
  EntityRelation,
  GoldLabel,
  RejectedRelation,
  SavedGoldEntity,
  GoldDialogSaveMode,
  GoldDialogEntitySaver,
  DualSaveEncounterContext,
} from "./types";
export {
  patchGoldLabelEntities,
  createGoldLabelFromDryRun,
  createGoldLabelFromEncounter,
  syncCodedLinksFromGold,
} from "./api";
export type {
  DryRunGoldLabelResponse,
  EncounterGoldLabelResponse,
  SyncCodedLinksResponse,
} from "./api";
