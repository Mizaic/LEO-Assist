/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A59215DA
 *   DI: DI-900CB621, DI-BE09736F
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A59215DA")
 */
"use client";

import { useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Typography from "@mui/material/Typography";
import dynamic from "next/dynamic";

import AreaIntro from "@/components/AreaIntro";

const BillingPage = dynamic(() => import("@/app/admin/billing/page"), { ssr: false });
const ModelsPage = dynamic(() => import("@/app/admin/models/page"), { ssr: false });
const DataQualityPage = dynamic(() => import("@/app/admin/data-quality/page"), { ssr: false });

const TABS = [
  { key: "billing", label: "Billing" },
  { key: "model-config", label: "Model Config" },
  { key: "data-quality", label: "Data Quality" },
];

export default function PlatformPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab") ?? "billing";
  const activeIdx = Math.max(0, TABS.findIndex((t) => t.key === tabParam));

  const handleTabChange = useCallback(
    (_: React.SyntheticEvent, newIdx: number) => {
      router.replace(`/admin/platform?tab=${TABS[newIdx].key}`);
    },
    [router]
  );

  return (
    <Box sx={{ minHeight: "100vh" }}>
      <Box sx={{ px: 3, pt: 3, pb: 0, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
        <AreaIntro area="platform" />
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 1.5 }}>
          Platform
        </Typography>
        <Tabs value={activeIdx} onChange={handleTabChange} variant="scrollable" scrollButtons="auto">
          {TABS.map((t) => (
            <Tab key={t.key} label={t.label} sx={{ textTransform: "none", fontSize: "0.875rem" }} />
          ))}
        </Tabs>
      </Box>

      <Box>
        {activeIdx === 0 && <BillingPage />}
        {activeIdx === 1 && <ModelsPage />}
        {activeIdx === 2 && <DataQualityPage />}
      </Box>
    </Box>
  );
}
