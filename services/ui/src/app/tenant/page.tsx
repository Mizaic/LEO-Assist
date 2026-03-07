"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * /tenant is superseded by /portal which supports both platform admins and org admins.
 * Redirect to maintain backwards compatibility with existing bookmarks and nav links.
 */
export default function TenantRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/portal");
  }, [router]);
  return null;
}
