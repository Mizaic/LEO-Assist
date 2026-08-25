/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */

export function workTaskSourceId(taskId: string): string {
  const sep = taskId.indexOf(":");
  if (sep < 0) return taskId;
  return taskId.slice(sep + 1);
}
