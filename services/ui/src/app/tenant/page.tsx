/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * /tenant is superseded by /portal which supports both platform admins and org admins.
 * Redirect to maintain backwards compatibility with existing bookmarks and nav links.
 */
export default function TenantRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/care/portal");
  }, [router]);
  return null;
}
