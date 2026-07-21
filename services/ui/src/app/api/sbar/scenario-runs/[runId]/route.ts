/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { type NextRequest, NextResponse } from "next/server";
import { proxySbarScenarioRequest } from "../_proxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ runId: string }> },
) {
  const { runId } = await context.params;
  if (!runId) {
    return NextResponse.json({ detail: "Missing runId" }, { status: 400 });
  }
  return proxySbarScenarioRequest(
    request,
    `/sbar/scenario-runs/${encodeURIComponent(runId)}`,
  );
}
