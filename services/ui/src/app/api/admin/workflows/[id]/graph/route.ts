/**
 * /api/admin/workflows/[id]/graph -- get and save the workflow node/edge graph.
 *
 * GET  -> Core API GET /admin/workflows/{id}/graph
 * PUT  -> Core API PUT /admin/workflows/{id}/graph
 */

import { NextRequest, NextResponse } from "next/server";
import { serverFetch } from "@/lib/serverFetch";

const API_BASE = (process.env.INTERNAL_API_BASE ?? "http://localhost:8000").replace(/\/+$/, "");

interface Params {
  params: Promise<{ id: string }>;
}

export async function GET(
  request: NextRequest,
  { params }: Params
): Promise<NextResponse> {
  const { id } = await params;
  const cookie = request.headers.get("cookie") ?? "";
  const res = await serverFetch(`${API_BASE}/admin/workflows/${id}/graph`, {
    headers: { Accept: "application/json", Cookie: cookie },
  });
  const data = await res.text();
  if (!res.ok) return NextResponse.json({ error: data }, { status: res.status });
  return new NextResponse(data, {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

export async function PUT(
  request: NextRequest,
  { params }: Params
): Promise<NextResponse> {
  const { id } = await params;
  const cookie = request.headers.get("cookie") ?? "";
  const body = await request.text();
  const res = await serverFetch(`${API_BASE}/admin/workflows/${id}/graph`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      Cookie: cookie,
    },
    body,
  });
  if (!res.ok) {
    const text = await res.text();
    return NextResponse.json({ error: text }, { status: res.status });
  }
  return new NextResponse(null, { status: 204 });
}
