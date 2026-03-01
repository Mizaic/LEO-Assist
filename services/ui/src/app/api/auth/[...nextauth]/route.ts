/**
 * Legacy NextAuth route - redirects to backend auth.
 * Kept for any existing links; new auth uses Python backend.
 */
import { NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function GET() {
  return NextResponse.redirect(`${API_BASE}/auth/login?next_url=/dashboard`);
}

export async function POST() {
  return NextResponse.redirect(`${API_BASE}/auth/login?next_url=/dashboard`);
}
