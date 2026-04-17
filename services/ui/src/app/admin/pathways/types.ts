/**
 * Shared types for the Pathways admin UI.
 *
 * Design Controls: DI-LEO-AI-150, DO-LEO-AI-146.
 */

export interface PlanDefinition {
  id: string;
  name: string;
  status: "draft" | "active" | "retired" | string;
  description?: string;
  version?: string;
  date?: string;
  source?: string;
  meta?: {
    seeded?: boolean;
    seededBy?: string;
    versionNotes?: string;
  };
  trigger?: { event?: string };
  actions?: Array<{ id: string }>;
  actionCount?: number;
}
