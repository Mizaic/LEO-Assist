/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { type NextRequest, NextResponse } from "next/server";
import { serverFetch } from "@/lib/serverFetch";

const CORE_API_BASE = (
  process.env.INTERNAL_API_BASE ??
  process.env.CORE_API_URL ??
  "http://localhost:8000"
).replace(/\/+$/, "");

export async function proxySbarScenarioRequest(
  request: NextRequest,
  path: string,
  init?: { method?: string; body?: string },
) {
  const cookie = request.headers.get("cookie") ?? "";
  const secret = process.env.SERVICE_AUTH_SECRET;
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    Cookie: cookie,
  };
  if (secret) headers.Authorization = `Bearer ${secret}`;

  let upstream: Response;
  try {
    upstream = await serverFetch(`${CORE_API_BASE}${path}`, {
      method: init?.method ?? request.method,
      headers,
      body: init?.body,
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
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
