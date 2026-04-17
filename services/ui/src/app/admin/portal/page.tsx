"use client";

import Box from "@mui/material/Box";

import OriginalPage from "@/app/portal/page";
import AreaIntro from "@/components/AreaIntro";

export default function AdminPortalPage() {
  return (
    <Box>
      <Box sx={{ px: { xs: 2, md: 3 }, pt: 2 }}>
        <AreaIntro area="portal" />
      </Box>
      <OriginalPage />
    </Box>
  );
}
