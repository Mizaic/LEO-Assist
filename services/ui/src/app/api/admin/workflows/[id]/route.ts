/**
 * /api/admin/workflows/[id] -- delete a single workflow.
 *
 * Proxies to the Core API at INTERNAL_API_BASE/admin/workflows/{id}.
 */

import { NextRequest, NextResponse } from "next/server";
import { serverFetch } from "@/lib/serverFetch";

const API_BASE = (process.env.INTERNAL_API_BASE ?? "http://localhost:8000").replace(/\/+$/, "");

interface Params {
  params: Promise<{ id: string }>;
}

export async function DELETE(
  request: NextRequest,
  { params }: Params
): Promise<NextResponse> {
  const { id } = await params;
  const cookie = request.headers.get("cookie") ?? "";
  const res = await serverFetch(`${API_BASE}/admin/workflows/${id}`, {
    method: "DELETE",
    headers: { Accept: "application/json", Cookie: cookie },
  });
  if (!res.ok) {
    const text = await res.text();
    return NextResponse.json({ error: text }, { status: res.status });
  }
  return new NextResponse(null, { status: 204 });
}
