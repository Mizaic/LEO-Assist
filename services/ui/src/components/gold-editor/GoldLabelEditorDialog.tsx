"use client";
/**
 * GoldLabelEditorDialog -- shared editor surface (DI-LEO-AI-219).
 *
 * Re-exports the canonical GoldLabelDetailDialog from
 * @/components/gold-dataset/GoldDatasetPanel under a stable name so
 * that consumers (Evaluate stage, /care/patients EncounterCard,
 * /care/encounters EncounterMissionControl, Candidates tab) all
 * import from one location.
 *
 * The dialog supports two save modes:
 *   - "gold" (default): persists via PATCH /training/gold-labels/{id}/entities.
 *   - "dual"          : caller injects an entitySaver that posts to
 *                       /patients/{p}/encounters/{e}/coded-links/sync-from-gold,
 *                       which writes both the live :DOCUMENTS rels
 *                       and the de-identified gold copy.
 *
 * R-LEO-AI-206 governs the safety controls on the dual-save path.
 */
import { GoldLabelDetailDialog } from "@/components/gold-dataset/GoldDatasetPanel";

export { GoldLabelDetailDialog as GoldLabelEditorDialog };
export default GoldLabelDetailDialog;
