/**
 * Proxy for GET /api/sbar/assessments/{assessmentId}
 *
 * Returns the persisted Assessment node so the playground can render the
 * full SBAR Markdown when a run completes (or partially completes).
 */
import { type NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const CORE_API_BASE = (
  process.env.CORE_API_URL ?? "http://localhost:8001"
).replace(/\/+$/, "");

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ assessmentId: string }> },
) {
  const { assessmentId } = await context.params;
  if (!assessmentId) {
    return NextResponse.json({ detail: "Missing assessmentId" }, { status: 400 });
  }
  const cookie = request.headers.get("cookie") ?? "";
  const secret = process.env.SERVICE_AUTH_SECRET;
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Requested-With": "XMLHttpRequest",
    Cookie: cookie,
  };
  if (secret) headers["Authorization"] = `Bearer ${secret}`;

  let upstream: Response;
  try {
    upstream = await fetch(
      `${CORE_API_BASE}/sbar/assessments/${encodeURIComponent(assessmentId)}`,
      { method: "GET", headers },
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
