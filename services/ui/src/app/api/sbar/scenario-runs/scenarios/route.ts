/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { type NextRequest } from "next/server";
import { proxySbarScenarioRequest } from "../_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.search;
  return proxySbarScenarioRequest(
    request,
    `/sbar/scenario-runs/scenarios${query}`,
  );
}
