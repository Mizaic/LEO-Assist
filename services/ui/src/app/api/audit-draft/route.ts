/**
 * SSE proxy for POST /api/audit-draft
 *
 * Forwards the draft request to the analytics API's audit-templates/draft
 * endpoint and pipes the SSE stream directly to the browser.
 *
 * Using a Route Handler (not middleware rewrite) so the long-lived SSE
 * connection is not subject to the middleware's internal socket timeout.
 *
 * Atlas trace:
 *   DO: DO-3775670C
 *   DI: DI-64CA7740
 */
import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function analyticsApi(): string {
  return (process.env.ANALYTICS_API_URL ?? "http://localhost:8003").replace(
    /\/+$/,
    "",
  );
}

export async function POST(request: NextRequest): Promise<NextResponse | Response> {
  const cookie = request.headers.get("cookie") ?? "";
  const body = await request.text();

  const secret = process.env.SERVICE_AUTH_SECRET;
  const outHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    Accept: "text/event-stream",
    Cookie: cookie,
  };
  if (secret) outHeaders["Authorization"] = `Bearer ${secret}`;

  let upstream: Response;
  try {
    upstream = await fetch(
      `${analyticsApi()}/analytics/audit-templates/draft`,
      {
        method: "POST",
        headers: outHeaders,
        body,
      },
    );
  } catch (err) {
    return NextResponse.json(
      { detail: `Analytics API unreachable: ${String(err)}` },
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

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
      Connection: "keep-alive",
    },
  });
}
