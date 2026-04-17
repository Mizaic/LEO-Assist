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
