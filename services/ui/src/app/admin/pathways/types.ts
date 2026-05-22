/**
 * Shared types for the Pathways admin UI.
 *
 * Design Controls: DI-LEO-AI-150, DO-LEO-AI-146.
 *
 * Atlas trace:
 *   DO: DO-11232EFB
 *   DI: DI-CD931485
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-11232EFB")
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
  _workflowMode?: "legacy_in_process" | "durable_pubsub" | string;
  _durableSteps?: Array<{
    step_id: string;
    event_type: string;
    loads?: string[];
    persists?: string[];
    emits_on_success?: string | null;
    emits_on_failure?: string | null;
    idempotency_key?: string;
  }>;
  _deprecatedSubgraphs?: string[];
}
