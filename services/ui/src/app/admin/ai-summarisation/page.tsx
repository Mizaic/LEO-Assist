/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import Box from "@mui/material/Box";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";

import { SegmentedTabs } from "@leo/design-system";

const SbarPlayground = dynamic(() => import("./SbarPlayground"), {
  ssr: false,
});
const ScenarioRunPanel = dynamic(() => import("./ScenarioRunPanel"), {
  ssr: false,
});

const TABS = [
  {
    id: "playground",
    label: "Playground",
    icon: <PlayArrowOutlinedIcon sx={{ fontSize: 16 }} />,
  },
  {
    id: "scenarios",
    label: "Scenario runs",
    icon: <ScienceOutlinedIcon sx={{ fontSize: 16 }} />,
  },
];

export default function AiSummarisationPage() {
  const [tab, setTab] = useState<"playground" | "scenarios">("playground");
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <SegmentedTabs
        tabs={TABS}
        value={tab}
        onChange={(id) => setTab(id as "playground" | "scenarios")}
        aria-label="AI summarisation views"
      />
      {tab === "playground" ? <SbarPlayground /> : <ScenarioRunPanel />}
    </Box>
  );
}
