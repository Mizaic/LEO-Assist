/**
 * Shared Ask LEO wait mark -- wordmark with a spinning O.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import { LeoLogo } from "@leo/design-system";

export function AskLeoBusyMark({
  variant = "light",
  height = 16,
  title = "Asking LEO",
}: {
  variant?: "dark" | "light";
  height?: number;
  title?: string;
}) {
  return (
    <LeoLogo height={height} variant={variant} spinning spinDuration={1.8} title={title} />
  );
}
