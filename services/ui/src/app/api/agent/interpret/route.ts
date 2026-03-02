/**
 * Proxy agent interpret requests to the backend.
 * Frontend calls /api/agent/interpret; this forwards to the Core API.
 */
import { NextRequest, NextResponse } from "next/server";

const API_BASE = (process.env.INTERNAL_API_BASE ?? "http://localhost:8000").replace(/\/+$/, "");

export async function POST(request: NextRequest) {
  const cookie = request.headers.get("cookie") ?? "";
  const body = await request.text();

  const res = await fetch(`${API_BASE}/agent/interpret`, {
    method: "POST",
    headers: {
      "Content-Type": request.headers.get("content-type") ?? "application/json",
      Accept: "application/json",
      Cookie: cookie,
    },
    body: body || undefined,
  });

  const data = await res.text();
  return new NextResponse(data, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("content-type") ?? "application/json",
    },
  });
}
