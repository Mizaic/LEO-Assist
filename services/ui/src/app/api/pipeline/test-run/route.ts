/**
 * Proxy for POST /api/pipeline/test-run  (non-streaming single-record dry-run)
 *
 * Forwards to the Pipeline Worker so that LLM/NLP work does not run on the
 * Core API process. The response is JSON (not SSE), so no special streaming
 * setup is needed — the worker may still take 30–60 s for a full pipeline run.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const PIPELINE_WORKER_BASE = (
  process.env.PIPELINE_WORKER_URL ?? "http://localhost:8006"
).replace(/\/+$/, "");

export async function POST(request: NextRequest) {
  const cookie = request.headers.get("cookie") ?? "";
  const body = await request.text();

  const secret = process.env.SERVICE_AUTH_SECRET;
  const outHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    Cookie: cookie,
  };
  if (secret) outHeaders["Authorization"] = `Bearer ${secret}`;

  let upstream: Response;
  try {
    upstream = await fetch(`${PIPELINE_WORKER_BASE}/test-run`, {
      method: "POST",
      headers: outHeaders,
      body,
    });
  } catch (err) {
    return NextResponse.json(
      { detail: `Pipeline Worker unreachable: ${String(err)}` },
      { status: 502 },
    );
  }

  const data = await upstream.text();
  return new NextResponse(data, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
