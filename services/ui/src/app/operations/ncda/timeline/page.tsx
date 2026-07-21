/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

import * as React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import NcdaPathwayTimeline from "@/components/ncda/NcdaPathwayTimeline";
import { NcdaPathway, PathwayBands } from "@/lib/ncdaPathway";

interface ApiResponse {
  pathways: NcdaPathway[];
  bands: Record<string, PathwayBands>;
}

async function fetchPathways(patientId: string): Promise<ApiResponse> {
  const res = await fetch(`/api/ncda/pathways?patient_id=${patientId}`, {
    cache: "no-store",
  });
  if (!res.ok) return { pathways: [], bands: {} };
  return res.json();
}

export default function NcdaTimelinePage({
  searchParams,
}: {
  searchParams?: { patient_id?: string };
}) {
  const [data, setData] = React.useState<ApiResponse>({ pathways: [], bands: {} });
  const patientId = searchParams?.patient_id ?? "";

  React.useEffect(() => {
    if (!patientId) return;
    fetchPathways(patientId).then(setData);
  }, [patientId]);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Cancer pathway timeline
      </Typography>
      <Typography variant="body1" color="text.secondary" gutterBottom>
        We show the four key steps the national audit measures. Hover a bar
        for the rule. Click an anchor for the supporting note.
      </Typography>
      {data.pathways.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          No pathways found for this patient yet.
        </Typography>
      )}
      {data.pathways.map((pathway, idx) => (
        <Box key={`${pathway.patient_id}-${idx}`} sx={{ mb: 3 }}>
          <NcdaPathwayTimeline
            pathway={pathway}
            bands={pathway.site_key ? data.bands[pathway.site_key] : null}
          />
        </Box>
      ))}
    </Box>
  );
}
