/**
 * Periodic /auth/session keepalive while the tab is visible.
 *
 * Server idle expiry only advances last_activity when /auth/session (or an
 * authenticated API dep) runs. Long local editing with few API calls still
 * needs this beat so the Redis idle window does not fire mid-task.
 *
 * Atlas trace:
 *   DO: DO-F7C82FB5
 *   DI: DI-8A96990F
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-F7C82FB5")
 */
"use client";

import { useEffect, useRef } from "react";

/** Default beat when idle timeout is unknown or zero (absolute TTL still applies). */
const FALLBACK_INTERVAL_MS = 5 * 60_000;
const MIN_INTERVAL_MS = 60_000;
const MAX_INTERVAL_MS = 10 * 60_000;

export function keepaliveIntervalMs(idleTimeoutMinutes: number): number {
  if (!Number.isFinite(idleTimeoutMinutes) || idleTimeoutMinutes <= 0) {
    return FALLBACK_INTERVAL_MS;
  }
  // Refresh at half the idle window, clamped so we neither spam nor lag.
  const half = (idleTimeoutMinutes * 60_000) / 2;
  return Math.min(MAX_INTERVAL_MS, Math.max(MIN_INTERVAL_MS, half));
}

export function useSessionKeepalive(
  enabled: boolean,
  idleTimeoutMinutes: number,
): void {
  const intervalMs = keepaliveIntervalMs(idleTimeoutMinutes);
  const inFlight = useRef(false);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    const ping = async () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        await fetch("/auth/session", { credentials: "include", cache: "no-store" });
      } catch {
        // Best-effort; next tick or API activity will retry.
      } finally {
        inFlight.current = false;
      }
    };

    const timer = window.setInterval(ping, intervalMs);
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        void ping();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    void ping();

    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, intervalMs]);
}
