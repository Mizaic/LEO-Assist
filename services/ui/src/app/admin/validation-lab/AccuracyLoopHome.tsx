/**
 * Validation Lab two-door home with gold and open-findings strip.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 */
"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CreateOutlinedIcon from "@mui/icons-material/CreateOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";

import type { LabCase } from "./labApi";
import { categoryLabel, type ValidationFinding } from "./findingTypes";

export type LabDoor = "rule" | "clinical" | "saved";

interface Props {
  goldCases: LabCase[];
  openFindings: ValidationFinding[];
  onOpenDoor: (door: LabDoor) => void;
  onOpenGold: (caseId: string) => void;
  onOpenFinding: (runId: string) => void;
}

export default function AccuracyLoopHome({
  goldCases,
  openFindings,
  onOpenDoor,
  onOpenGold,
  onOpenFinding,
}: Props) {
  return (
    <Box data-testid="validation-lab-home">
      <Typography variant="h5" fontWeight={700} sx={{ mb: 0.5 }}>
        Validation Lab
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: 560 }}>
        Check that LEO reads a letter the way you would. Pick one path.
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
          gap: 2,
          mb: 3,
        }}
      >
        <DoorCard
          testId="validation-lab-mode-rule"
          color="#1E40AF"
          icon={<CreateOutlinedIcon sx={{ fontSize: 28, color: "#1E40AF" }} />}
          headline="Test a guideline rule"
          description="Pick a care rule. Check the letter. Run the same path a real referral uses."
          steps={[
            "1. Pick a guideline rule",
            "2. Check the letter",
            "3. Review each step",
            "4. Fix, retest, save gold",
          ]}
          onClick={() => onOpenDoor("rule")}
        />
        <DoorCard
          testId="validation-lab-mode-clinical"
          color="#9D174D"
          icon={<FolderOpenOutlinedIcon sx={{ fontSize: 28, color: "#9D174D" }} />}
          headline="Investigate a clinical complaint"
          description="Find the patient by NHS number or referral number, or pick from the list. Mark what went wrong. Do not start a new job."
          steps={[
            "1. Enter NHS number or referral number, or pick a patient",
            "2. Say why you opened it",
            "3. Mark what is wrong",
            "4. Fix, then retest if needed",
          ]}
          onClick={() => onOpenDoor("clinical")}
        />
      </Box>
      <HomeStrip
        goldCases={goldCases}
        openFindings={openFindings}
        onOpenGold={onOpenGold}
        onOpenFinding={onOpenFinding}
        onBrowseSaved={() => onOpenDoor("saved")}
      />
    </Box>
  );
}

function DoorCard({
  testId,
  color,
  icon,
  headline,
  description,
  steps,
  onClick,
}: {
  testId: string;
  color: string;
  icon: React.ReactNode;
  headline: string;
  description: string;
  steps: string[];
  onClick: () => void;
}) {
  return (
    <Box
      onClick={onClick}
      data-testid={testId}
      sx={{
        p: 3,
        border: "2px solid",
        borderColor: "divider",
        borderRadius: "14px",
        cursor: "pointer",
        "&:hover": { borderColor: color, boxShadow: `0 4px 20px ${color}18` },
      }}
    >
      <Stack direction="row" spacing={2} sx={{ mb: 1.5 }}>
        <Box
          sx={{
            width: 48,
            height: 48,
            borderRadius: "12px",
            bgcolor: `${color}14`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {icon}
        </Box>
        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            {headline}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {description}
          </Typography>
        </Box>
      </Stack>
      {steps.map((step) => (
        <Typography key={step} variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
          {step}
        </Typography>
      ))}
    </Box>
  );
}

function HomeStrip({
  goldCases,
  openFindings,
  onOpenGold,
  onOpenFinding,
  onBrowseSaved,
}: {
  goldCases: LabCase[];
  openFindings: ValidationFinding[];
  onOpenGold: (caseId: string) => void;
  onOpenFinding: (runId: string) => void;
  onBrowseSaved: () => void;
}) {
  return (
    <Box
      sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: "12px" }}
      data-testid="validation-lab-home-strip"
    >
      <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
        Saved gold cases
      </Typography>
      {goldCases.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          None yet. Save gold after a run looks right.
        </Typography>
      ) : (
        goldCases.slice(0, 6).map((row) => (
          <Typography
            key={row.id}
            variant="body2"
            sx={{ cursor: "pointer", mb: 0.5 }}
            onClick={() => onOpenGold(row.id)}
          >
            {row.title}
          </Typography>
        ))
      )}
      <Typography
        variant="body2"
        color="primary"
        sx={{ cursor: "pointer", mb: 2 }}
        onClick={onBrowseSaved}
        data-testid="validation-lab-browse-saved"
      >
        Open saved tests
      </Typography>
      <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
        Open findings
      </Typography>
      {openFindings.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No open findings.
        </Typography>
      ) : (
        openFindings.slice(0, 8).map((row) => (
          <Typography
            key={row.id}
            variant="body2"
            sx={{ cursor: "pointer", mb: 0.5 }}
            onClick={() => onOpenFinding(row.run_id)}
          >
            {categoryLabel(row.category)} -- {row.target || row.note || row.run_id}
          </Typography>
        ))
      )}
    </Box>
  );
}
