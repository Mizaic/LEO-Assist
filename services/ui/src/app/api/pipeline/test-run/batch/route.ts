/**
 * Streaming proxy for POST /api/pipeline/test-run/batch
 *
 * Batch dry-runs invoke LLM calls, spaCy NLP, and Neo4j queries for every
 * candidate. Running that on the Core API (port 8000) would compete with live
 * request serving — instead, this route forwards the request to the dedicated
 * Pipeline Worker (port 8006), which exposes the same SSE endpoint alongside
 * its message bus consumer.
 *
 * The Next.js middleware proxy (NextResponse.rewrite) has a socket timeout
 * that kills long-lived SSE streams. This Route Handler bypasses the
 * middleware entirely and pipes the upstream body stream directly back with
 * no intermediary buffering or timeout.
 *
 * Next.js App Router Route Handlers take precedence over middleware for
 * matching paths, so this file shadows the generic /api/pipeline/** rewrite.
 */
import { type NextRequest, NextResponse } from "next/server";

// Opt out of static generation — this is always a live proxied request.
export const dynamic = "force-dynamic";

// Pipeline Worker exposes HTTP on a separate port so batch work never touches
// the Core API process. Falls back to 8006 for local dev.
const PIPELINE_WORKER_BASE = (
  process.env.PIPELINE_WORKER_URL ?? "http://localhost:8006"
).replace(/\/+$/, "");

export async function POST(request: NextRequest) {
  const cookie = request.headers.get("cookie") ?? "";
  const body = await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${PIPELINE_WORKER_BASE}/test-run/batch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        Accept: "text/event-stream",
        Cookie: cookie,
      },
      body,
      // Node 18+ fetch: disable response body timeout so the stream can run
      // for as long as the backend needs.
      // @ts-expect-error — Next.js exposes this non-standard option
      signal: null,
    });
  } catch (err) {
    return NextResponse.json(
      { detail: `Failed to reach pipeline API: ${String(err)}` },
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

  // Pipe the backend SSE body stream straight to the client.
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
