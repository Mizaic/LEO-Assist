/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-47454249
 *   DI: DI-E5FEF0AE
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-47454249")
 */
"use client";

import { useEffect, useState } from "react";
import { LeoLogo } from "./LeoLogo";
import "./leo-logo.css";

export type LeoSplashProps = {
  /** When set, the parent controls visibility. Omit to auto-dismiss after minDurationMs. */
  visible?: boolean;
  minDurationMs?: number;
  fadeMs?: number;
  logoHeight?: number;
  onDismiss?: () => void;
};

export function LeoSplash({
  visible,
  minDurationMs = 2200,
  fadeMs = 480,
  logoHeight = 96,
  onDismiss,
}: LeoSplashProps) {
  const controlled = visible !== undefined;
  const [phase, setPhase] = useState<"in" | "out" | "gone">("in");

  useEffect(() => {
    if (controlled) return;
    const fade = window.setTimeout(() => setPhase("out"), minDurationMs);
    return () => window.clearTimeout(fade);
  }, [controlled, minDurationMs]);

  useEffect(() => {
    if (!controlled) return;
    if (visible) {
      setPhase("in");
      return;
    }
    setPhase((current) => (current === "gone" ? "gone" : "out"));
  }, [controlled, visible]);

  useEffect(() => {
    if (phase !== "out") return;
    const gone = window.setTimeout(() => {
      setPhase("gone");
      onDismiss?.();
    }, fadeMs);
    return () => window.clearTimeout(gone);
  }, [phase, fadeMs, onDismiss]);

  if (phase === "gone") return null;

  return (
    <div
      className="leo-splash"
      data-leaving={phase === "out"}
      style={{ ["--leo-splash-fade" as string]: `${fadeMs}ms` }}
      role="status"
      aria-label="Loading LEO"
    >
      <LeoLogo height={logoHeight} spinning />
    </div>
  );
}
