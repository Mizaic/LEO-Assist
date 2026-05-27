/**
 * Inline completeness pill for the SBAR Background section header.
 *
 * Shows a percentage chip (green/amber/red) that, on hover, expands
 * into a tooltip listing each required field as present, missing, or
 * unclear. Data comes from the server-computed CompletenessFinding
 * shape (libs/pipeline_graph/subgraphs/quality_check.py).
 *
 * Atlas trace:
 *   DI: DI-B883B2BE (render completeness findings and completeness chip)
 *   DO: DO-D5DDC2CF
 *   VT: VT-1AA1E176
 */
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

export interface CompletenessFinding {
  requiredFields: string[];
  presentFields: string[];
  missingFields: string[];
  unclearFields: string[];
}

function _pct(finding: CompletenessFinding): number {
  const total = finding.requiredFields.length;
  if (total === 0) return 100;
  return Math.round((finding.presentFields.length / total) * 100);
}

function _chipColor(pct: number): "success" | "warning" | "error" {
  if (pct >= 100) return "success";
  if (pct >= 50) return "warning";
  return "error";
}

function TooltipContent({ finding }: { finding: CompletenessFinding }) {
  const total = finding.requiredFields.length;
  return (
    <Box sx={{ p: 0.25 }}>
      <Typography
        variant="caption"
        sx={{ fontWeight: 700, display: "block", mb: 0.5 }}
      >
        {`Referral completeness: ${finding.presentFields.length} of ${total} required fields`}
      </Typography>
      {finding.presentFields.map((f) => (
        <Typography
          key={f}
          variant="caption"
          sx={{ display: "block", color: "#4ade80" }}
        >
          {"\u2713 " + f}
        </Typography>
      ))}
      {finding.missingFields.map((f) => (
        <Typography
          key={f}
          variant="caption"
          sx={{ display: "block", color: "#fca5a5" }}
        >
          {"\u2717 " + f + " (required - missing)"}
        </Typography>
      ))}
      {finding.unclearFields.map((f) => (
        <Typography
          key={f}
          variant="caption"
          sx={{ display: "block", color: "#fcd34d" }}
        >
          {"~ " + f + " (optional - not found)"}
        </Typography>
      ))}
    </Box>
  );
}

export interface CompletenessPillProps {
  finding: CompletenessFinding;
  testIdPrefix?: string;
}

export function CompletenessPill({
  finding,
  testIdPrefix = "sbar-final",
}: CompletenessPillProps) {
  const pct = _pct(finding);
  return (
    <Tooltip
      title={<TooltipContent finding={finding} />}
      placement="left"
      arrow
    >
      <Chip
        size="small"
        label={`${pct}%`}
        color={_chipColor(pct)}
        data-testid={`${testIdPrefix}-completeness-chip`}
        sx={{ height: 20, fontSize: "0.65rem", cursor: "default" }}
      />
    </Tooltip>
  );
}
