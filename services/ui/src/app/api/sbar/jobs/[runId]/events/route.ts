/**
 * Streaming proxy for GET /api/sbar/jobs/{runId}/events
 *
 * Pipes the Core API SSE stream (sbar_started -> sbar_stage_started ->
 * sbar_stage_completed -> sbar_completed) directly to the browser.
 * Long-lived stream so we use a Route Handler rather than the global
 * middleware proxy (the middleware would drop the connection at ~30 s).
 *
 * See DI-LEO-AI-191 / DI-LEO-AI-194.
 */
import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const CORE_API_BASE = (
  process.env.CORE_API_URL ?? "http://localhost:8001"
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
      `${CORE_API_BASE}/sbar/jobs/${encodeURIComponent(runId)}/events`,
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
