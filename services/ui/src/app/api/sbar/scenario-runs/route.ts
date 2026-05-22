import { type NextRequest } from "next/server";
import { proxySbarScenarioRequest } from "./_proxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.search;
  return proxySbarScenarioRequest(request, `/sbar/scenario-runs${query}`);
}

export async function POST(request: NextRequest) {
  return proxySbarScenarioRequest(request, "/sbar/scenario-runs", {
    method: "POST",
    body: await request.text(),
  });
}
