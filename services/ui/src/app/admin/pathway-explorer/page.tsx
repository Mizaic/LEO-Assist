/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-3AD4D385
 *   Also implements: DO-A59215DA
 *   DI: DI-900CB621, DI-9DCBC4BA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-3AD4D385")
 */
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
