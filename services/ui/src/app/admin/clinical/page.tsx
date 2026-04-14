"use client";

import { useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import Typography from "@mui/material/Typography";
import dynamic from "next/dynamic";

const PathwaysPage = dynamic(() => import("@/app/admin/pathways/page"), { ssr: false });
const DomainsPage = dynamic(() => import("@/app/admin/domains/page"), { ssr: false });
const TerminologyPage = dynamic(() => import("@/app/admin/terminology/page"), { ssr: false });

const TABS = [
  { key: "pathways", label: "Pathways" },
  { key: "domains", label: "Domains" },
  { key: "terminology", label: "Terminology" },
];

export default function ClinicalPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab") ?? "pathways";
  const activeIdx = Math.max(0, TABS.findIndex((t) => t.key === tabParam));

  const handleTabChange = useCallback(
    (_: React.SyntheticEvent, newIdx: number) => {
      router.replace(`/admin/clinical?tab=${TABS[newIdx].key}`);
    },
    [router]
  );

  return (
    <Box sx={{ minHeight: "100vh" }}>
      <Box sx={{ px: 3, pt: 3, pb: 0, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 1.5 }}>
          Clinical Setup
        </Typography>
        <Tabs value={activeIdx} onChange={handleTabChange} variant="scrollable" scrollButtons="auto">
          {TABS.map((t) => (
            <Tab key={t.key} label={t.label} sx={{ textTransform: "none", fontSize: "0.875rem" }} />
          ))}
        </Tabs>
      </Box>

      <Box>
        {activeIdx === 0 && <PathwaysPage />}
        {activeIdx === 1 && <DomainsPage />}
        {activeIdx === 2 && <TerminologyPage />}
      </Box>
    </Box>
  );
}
