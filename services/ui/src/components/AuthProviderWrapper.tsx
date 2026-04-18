"use client";

import { AuthProvider, type Session } from "@/lib/authContext";

export default function AuthProviderWrapper({
  children,
  initialSession = null,
}: {
  children: React.ReactNode;
  initialSession?: Session | null;
}) {
  return <AuthProvider initialSession={initialSession}>{children}</AuthProvider>;
}
