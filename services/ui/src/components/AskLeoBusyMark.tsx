/**
 * Shared Ask LEO wait mark -- wordmark with a spinning O.
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
