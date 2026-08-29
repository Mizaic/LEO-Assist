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
    `hosts/${encodeURIComponent(hostId)}/artefacts`,
    body,
  );
}
