/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
// -- editor/utils.ts -----------------------------------------------------------
// Small pure helpers shared by the pathway editor chrome (toolbar, save bar,
// dialogs). Kept colocated with the editor so the orchestrator stays small.

export function formatSaveTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export type PlanLifecycleStatus = "draft" | "active" | "retired";

export function lifecycleLabel(status: PlanLifecycleStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function lifecycleColor(
  status: PlanLifecycleStatus,
): "success" | "default" | "warning" {
  if (status === "active") return "success";
  if (status === "retired") return "default";
  return "warning";
}
