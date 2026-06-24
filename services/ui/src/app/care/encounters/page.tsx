/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-F78C84A6
 *   DI: DI-D0FC22FE
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-F78C84A6")
 *
 * Encounters has moved to /admin/encounters. This redirect keeps legacy
 * bookmarks and linked reports working while the nav is updated.
 */
import { redirect } from "next/navigation";

export default function CareEncountersRedirect() {
  redirect("/admin/encounters");
}
