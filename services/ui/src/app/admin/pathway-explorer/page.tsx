"use client";

import dynamic from "next/dynamic";

const PathwayExplorerWorkspace = dynamic(
  () => import("@/components/research/PathwayExplorerWorkspace"),
  { ssr: false }
);

export default function PathwayExplorerPage() {
  return <PathwayExplorerWorkspace />;
}
