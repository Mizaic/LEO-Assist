/**
 * Atlas trace:
 *   DO: DO-6F6771E5
 *   DI: DI-14809BB8
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-6F6771E5")
 */
import { type NextRequest } from "next/server";
import { proxyGovernance } from "../../../_proxy";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ hostId: string }> },
) {
  const { hostId } = await params;
  const body = await request.text();
  return proxyGovernance(
    request,
    `hosts/${encodeURIComponent(hostId)}/ifu`,
    body,
  );
}
