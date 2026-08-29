import { type NextRequest } from "next/server";
import { proxyGovernance } from "../_proxy";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = await request.text();
  return proxyGovernance(request, "hosts", body);
}
