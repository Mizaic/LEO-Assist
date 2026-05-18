"use client";

import * as React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import NcdaAuditTile, {
  NcdaAuditFinding,
  ReviewerAction,
} from "@/components/ncda/NcdaAuditTile";

async function fetchFindings(): Promise<NcdaAuditFinding[]> {
  try {
    const res = await fetch("/api/ncda/audit", { cache: "no-store" });
    if (!res.ok) return [];
    const body = await res.json();
    return Array.isArray(body.items) ? body.items : [];
  } catch {
    return [];
  }
}

async function postAction(finding: NcdaAuditFinding, action: ReviewerAction) {
  await fetch("/api/ncda/audit/action", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      patient_id: finding.patient_id,
      encounter_id: finding.encounter_id,
      finding_type: finding.finding_type,
      episode_id: finding.episode_id,
      action,
    }),
  });
}

export default function NcdaAuditPage() {
  const [findings, setFindings] = React.useState<NcdaAuditFinding[]>([]);

  React.useEffect(() => {
    let mounted = true;
    fetchFindings().then((rows) => {
      if (mounted) setFindings(rows);
    });
    return () => {
      mounted = false;
    };
  }, []);

  const handleAction = async (
    finding: NcdaAuditFinding,
    action: ReviewerAction,
  ) => {
    await postAction(finding, action);
    setFindings((prev) =>
      prev.filter(
        (f) =>
          !(
            f.patient_id === finding.patient_id &&
            f.encounter_id === finding.encounter_id &&
            f.finding_type === finding.finding_type
          ),
      ),
    );
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Cancer pathway audit
      </Typography>
      <Typography variant="body1" color="text.secondary" gutterBottom>
        Review what the computer found odd in the labelled records. Fixing
        these helps the model learn faster.
      </Typography>
      <NcdaAuditTile findings={findings} onAction={handleAction} />
    </Box>
  );
}
