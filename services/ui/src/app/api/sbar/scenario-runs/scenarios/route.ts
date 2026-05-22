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
