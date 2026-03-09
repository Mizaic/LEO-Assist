/**
 * Streaming proxy for POST /api/pipeline/test-run/stream
 *
 * Forwards to the Pipeline Worker (not the Core API) so that LLM calls and
 * spaCy NLP processing do not compete with live API request serving.
 *
 * Uses a Route Handler rather than the middleware rewrite so the SSE stream
 * is piped directly — the middleware's internal socket timeout would kill
 * runs longer than ~30 s (e.g. when verification or terminology are slow).
 */
import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const PIPELINE_WORKER_BASE = (
  process.env.PIPELINE_WORKER_URL ?? "http://localhost:8006"
).replace(/\/+$/, "");

export async function POST(request: NextRequest) {
  const cookie = request.headers.get("cookie") ?? "";
  const body = await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${PIPELINE_WORKER_BASE}/test-run/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        Accept: "text/event-stream",
        Cookie: cookie,
      },
      body,
      // @ts-expect-error — disable fetch abort so long streams aren't cut short
      signal: null,
    });
  } catch (err) {
    return NextResponse.json(
      { detail: `Pipeline Worker unreachable: ${String(err)}` },
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
