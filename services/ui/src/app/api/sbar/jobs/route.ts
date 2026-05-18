/**
 * Proxy for POST /api/sbar/jobs
 *
 * Forwards to the Core API which validates the SBARRequestPayload and
 * publishes an `sbar_requested` message onto the pipeline-jobs queue.
 *
 * Per DI-LEO-AI-194 (AI Summarisation Playground): the playground POSTs
 * the selected situation/background/guideline IDs here. The Core API
 * round-trip is fast (it only enqueues), so no streaming is needed.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { type NextRequest, NextResponse } from "next/server";
import { serverFetch } from "@/lib/serverFetch";

export const dynamic = "force-dynamic";

// Core API runs on :8000 (terminology-api is :8001). Match the repo
// convention used by services/ui/src/proxy.ts -- INTERNAL_API_BASE is
// the canonical env var; CORE_API_URL is a backwards-compatible alias.
const CORE_API_BASE = (
  process.env.INTERNAL_API_BASE ??
  process.env.CORE_API_URL ??
  "http://localhost:8000"
).replace(/\/+$/, "");

export async function POST(request: NextRequest) {
  const cookie = request.headers.get("cookie") ?? "";
  const body = await request.text();

  const secret = process.env.SERVICE_AUTH_SECRET;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    Cookie: cookie,
  };
  if (secret) headers["Authorization"] = `Bearer ${secret}`;

  let upstream: Response;
  try {
    upstream = await serverFetch(`${CORE_API_BASE}/sbar/jobs`, {
      method: "POST",
      headers,
      body,
    });
  } catch (err) {
    return NextResponse.json(
      { detail: `Core API unreachable: ${String(err)}` },
      { status: 502 },
    );
  }
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
