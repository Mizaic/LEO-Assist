import { type NextRequest } from "next/server";
import { proxyGovernance } from "../_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return proxyGovernance(request, "register");
}
