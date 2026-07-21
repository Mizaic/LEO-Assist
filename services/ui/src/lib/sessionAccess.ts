/**
 * Access gate helpers for authenticated sessions.
 *
 * A Microsoft login alone is not enough. Non-admin users need at least one
 * LEO role before the shell may paint protected clinical chrome.
 *
 * Atlas trace:
 *   DO: DO-FDC2F8CC
 *   DI: DI-C04323B0
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-FDC2F8CC")
 */

import type { Session } from "@/lib/authContext";

export function sessionHasLeoAccess(session: Session | null | undefined): boolean {
  if (!session) return false;
  if (session.isPlatformAdmin) return true;
  return session.allowedRoles.length > 0;
}
