/**
 * /api/admin/workflows -- list and create workflows.
 *
 * Proxies to the Core API at INTERNAL_API_BASE/admin/workflows.
 * Platform admin role is enforced server-side by the Core API.
 */

import { NextRequest, NextResponse } from "next/server";
import { serverFetch } from "@/lib/serverFetch";

const API_BASE = (process.env.INTERNAL_API_BASE ?? "http://localhost:8000").replace(/\/+$/, "");

function forwardError(status: number, text: string): NextResponse {
  return NextResponse.json({ error: text }, { status });
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const cookie = request.headers.get("cookie") ?? "";
  const res = await serverFetch(`${API_BASE}/admin/workflows`, {
    headers: { Accept: "application/json", Cookie: cookie },
  });
  const data = await res.text();
  if (!res.ok) return forwardError(res.status, data);
  return new NextResponse(data, {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const cookie = request.headers.get("cookie") ?? "";
  const body = await request.text();
  const res = await serverFetch(`${API_BASE}/admin/workflows`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      Cookie: cookie,
    },
    body,
  });
  const data = await res.text();
  if (!res.ok) return forwardError(res.status, data);
  return new NextResponse(data, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
