/**
 * Streaming proxy for GET /api/training/candidates/ai-first-pass/jobs/{runId}/events
 *
 * Pipes the Core API SSE stream (candidate.processed -> job.summary)
 * directly to the browser. Long-lived stream, so we use an explicit
 * Route Handler rather than the global middleware proxy (which would
 * drop the connection at ~30s).
 *
 * Per DI-LEO-AI-209 / DO-LEO-AI-206.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const CORE_API_BASE = (
  process.env.INTERNAL_API_BASE ?? "http://localhost:8000"
).replace(/\/+$/, "");

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ runId: string }> },
) {
  const { runId } = await context.params;
  if (!runId) {
    return NextResponse.json({ detail: "Missing runId" }, { status: 400 });
  }
  const cookie = request.headers.get("cookie") ?? "";
  const secret = process.env.SERVICE_AUTH_SECRET;
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "X-Requested-With": "XMLHttpRequest",
    Cookie: cookie,
  };
  if (secret) headers["Authorization"] = `Bearer ${secret}`;

  let upstream: Response;
  try {
    upstream = await fetch(
      `${CORE_API_BASE}/training/candidates/ai-first-pass/jobs/${encodeURIComponent(
        runId,
      )}/events`,
      { method: "GET", headers },
    );
  } catch (err) {
    return NextResponse.json(
      { detail: `Core API unreachable: ${String(err)}` },
      { status: 502 },
    );
  }
  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }
  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
      Connection: "keep-alive",
    },
  });
}
