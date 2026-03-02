/**
 * Idle-logout hook.
 *
 * After `idleMinutes` of no mouse/keyboard/touch activity:
 *   1. Sets `isWarning = true` so the caller can show a "Still there?" dialog.
 *   2. After WARN_GRACE_MS more ms of silence, calls `onLogout`.
 *
 * Call `keepAlive()` when the user acknowledges the warning to reset.
 * Set `idleMinutes` to 0 to disable entirely.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const WARN_GRACE_MS = 120_000; // 2 min warning window before forced logout

const ACTIVITY_EVENTS = [
  "mousemove",
  "mousedown",
  "keydown",
  "touchstart",
  "scroll",
] as const;

export function useIdleLogout(
  idleMinutes: number,
  onLogout: () => void,
): { isWarning: boolean; keepAlive: () => void } {
  const [isWarning, setIsWarning] = useState(false);
  const idleTimer = useRef<ReturnType<typeof setTimeout>>();
  const warnTimer = useRef<ReturnType<typeof setTimeout>>();

  const clearTimers = useCallback(() => {
    clearTimeout(idleTimer.current);
    clearTimeout(warnTimer.current);
  }, []);

  const keepAlive = useCallback(() => {
    if (idleMinutes <= 0) return;
    clearTimers();
    setIsWarning(false);
    idleTimer.current = setTimeout(() => {
      setIsWarning(true);
      warnTimer.current = setTimeout(onLogout, WARN_GRACE_MS);
    }, idleMinutes * 60_000);
  }, [idleMinutes, clearTimers, onLogout]);

  useEffect(() => {
    if (idleMinutes <= 0) return;
    const handler = () => keepAlive();
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, handler, { passive: true }));
    keepAlive();
    return () => {
      clearTimers();
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, handler));
    };
  }, [idleMinutes, keepAlive, clearTimers]);

  return { isWarning, keepAlive };
}
