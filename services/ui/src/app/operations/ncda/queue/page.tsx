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

import NcdaQueueTile, { NcdaQueueItem } from "@/components/ncda/NcdaQueueTile";

async function fetchQueue(): Promise<NcdaQueueItem[]> {
  try {
    const res = await fetch("/api/ncda/queue", { cache: "no-store" });
    if (!res.ok) return [];
    const body = await res.json();
    return Array.isArray(body.items) ? body.items : [];
  } catch {
    return [];
  }
}

export default function NcdaQueuePage() {
  const [items, setItems] = React.useState<NcdaQueueItem[]>([]);

  React.useEffect(() => {
    let mounted = true;
    fetchQueue().then((rows) => {
      if (mounted) setItems(rows);
    });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Cases to review
      </Typography>
      <Typography variant="body1" color="text.secondary" gutterBottom>
        These are pathways where the computer is unsure. Your check makes
        the next run more accurate.
      </Typography>
      <NcdaQueueTile items={items} />
    </Box>
  );
}
