/**
 * GET /sdk/sbar/[assessmentId]
 *
 * Proxy for the <leo-sbar> web component's data fetch.
 * The widget calls GET {proxy-origin}/sdk/sbar/{id} with
 * Authorization: Bearer {widget_token}.
 * This handler forwards that token to the Core API's
 * GET /sdk/sbar/{assessmentId} endpoint and returns the response.
 *
 * No Next.js session required -- the widget token is the only credential.
 */
import { type NextRequest, NextResponse } from "next/server";
import { serverFetch } from "@/lib/serverFetch";

export const dynamic = "force-dynamic";

const CORE_API_BASE = (
  process.env.INTERNAL_API_BASE ??
  process.env.CORE_API_URL ??
  "http://localhost:8000"
).replace(/\/+$/, "");

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ assessmentId: string }> },
) {
  const { assessmentId } = await params;
  const authorization = request.headers.get("authorization") ?? "";

  let upstream: Response;
  try {
    upstream = await serverFetch(
      `${CORE_API_BASE}/sdk/sbar/${encodeURIComponent(assessmentId)}`,
      {
        method: "GET",
        headers: {
          Authorization: authorization,
          Accept: "application/json",
        },
      },
    );
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
