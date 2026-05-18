/**
 * Public surface for the shared gold-label editor (DI-LEO-AI-219).
 *
 * Consumers should import only from this barrel:
 *
 *   import {
 *     GoldLabelEditorDialog,
 *     useDualSaveAdapter,
 *     createGoldLabelFromEncounter,
 *     syncCodedLinksFromGold,
 *   } from "@/components/gold-editor";
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
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
