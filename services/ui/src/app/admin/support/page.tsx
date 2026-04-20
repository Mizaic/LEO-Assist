/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A59215DA
 *   DI: DI-900CB621
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A59215DA")
 */
"use client";

import Box from "@mui/material/Box";

import OriginalPage from "@/app/mail/page";
import AreaIntro from "@/components/AreaIntro";

export default function AdminSupportPage() {
  return (
    <Box>
      <Box sx={{ px: { xs: 2, md: 3 }, pt: 2 }}>
        <AreaIntro area="support" />
      </Box>
      <OriginalPage />
    </Box>
  );
}
