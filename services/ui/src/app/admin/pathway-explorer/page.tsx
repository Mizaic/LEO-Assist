"use client";

import dynamic from "next/dynamic";
import Box from "@mui/material/Box";

import AreaIntro from "@/components/AreaIntro";

const PathwayExplorerWorkspace = dynamic(
  () => import("@/components/research/PathwayExplorerWorkspace"),
  { ssr: false }
);

export default function PathwayExplorerPage() {
  return (
    <Box>
      <Box sx={{ px: { xs: 2, md: 3 }, pt: 2 }}>
        <AreaIntro area="pathway-explorer" />
      </Box>
      <PathwayExplorerWorkspace />
    </Box>
  );
}
