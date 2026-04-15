"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Typography from "@mui/material/Typography";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import type { DetailLevel, MissionDescription, PersonaLens } from "@/lib/researchApi";
import type { ScopingParams } from "./useResearchState";

interface Props {
  open: boolean;
  mission: MissionDescription | null;
  lens: PersonaLens;
  scoping: ScopingParams;
  onClose: () => void;
  onUpdate: (params: Partial<ScopingParams>) => void;
  onSubmit: () => void;
}

const AREAS = [
  { value: "all", label: "All pathways" },
  { value: "lung", label: "Lung" },
  { value: "colorectal", label: "Colorectal" },
  { value: "breast", label: "Breast" },
  { value: "prostate", label: "Prostate" },
  { value: "upper_gi", label: "Upper GI" },
  { value: "gynaecology", label: "Gynaecology" },
  { value: "urology", label: "Urology" },
  { value: "head_neck", label: "Head & neck" },
  { value: "skin", label: "Skin" },
  { value: "haematology", label: "Haematology" },
];

const PERIODS = [
  { value: "3m", label: "Last 3 months" },
  { value: "6m", label: "Last 6 months" },
  { value: "12m", label: "Last 12 months" },
];

const DETAILS: Array<{ value: DetailLevel; label: string; hint: string }> = [
  {
    value: "summary",
    label: "Summary",
    hint: "Top 10 results, grouped",
  },
  {
    value: "detailed",
    label: "Detailed",
    hint: "Top 50 individual results",
  },
  {
    value: "everything",
    label: "Everything",
    hint: "All results (may be slow)",
  },
];

const CONTEXT_OPTIONS: Array<{
  value: "current" | "all";
  label: string;
  hint: string;
}> = [
  {
    value: "current",
    label: "Active conditions only",
    hint: "Current diagnoses and findings",
  },
  {
    value: "all",
    label: "Include historical",
    hint: "Past and family history too",
  },
];

export default function ScopingWizard({
  open,
  mission,
  lens,
  scoping,
  onClose,
  onUpdate,
  onSubmit,
}: Props) {
  const title =
    mission?.titles[lens] ?? mission?.titles.patients ?? "Start investigation";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      aria-labelledby="scoping-dialog-title"
    >
      <DialogTitle id="scoping-dialog-title">
        <Typography
          component="span"
          variant="h6"
          sx={{ fontWeight: 700, lineHeight: 1.3, display: "block" }}
        >
          {title}
        </Typography>
        <Typography
          component="span"
          variant="body2"
          sx={{ color: "text.secondary", mt: 0.5, display: "block" }}
        >
          Choose what to focus your investigation on.
        </Typography>
      </DialogTitle>

      <DialogContent dividers sx={{ py: 3 }}>
        {/* Question 1: Which area? */}
        <ScopingQuestion label="Which area?">
          <ToggleButtonGroup
            value={scoping.area}
            exclusive
            onChange={(_, v) => v && onUpdate({ area: v })}
            size="small"
            sx={{ flexWrap: "wrap", gap: 0.75 }}
          >
            {AREAS.map((a) => (
              <ToggleButton
                key={a.value}
                value={a.value}
                sx={pillSx}
                aria-label={a.label}
              >
                {a.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </ScopingQuestion>

        {/* Question 2: Which time period? */}
        <ScopingQuestion label="Which time period?">
          <ToggleButtonGroup
            value={scoping.period}
            exclusive
            onChange={(_, v) => v && onUpdate({ period: v })}
            size="small"
            sx={{ flexWrap: "wrap", gap: 0.75 }}
          >
            {PERIODS.map((p) => (
              <ToggleButton
                key={p.value}
                value={p.value}
                sx={pillSx}
                aria-label={p.label}
              >
                {p.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </ScopingQuestion>

        {/* Question 3: How much detail? */}
        <ScopingQuestion label="How much detail?">
          <ToggleButtonGroup
            value={scoping.detail}
            exclusive
            onChange={(_, v) => v && onUpdate({ detail: v as DetailLevel })}
            size="small"
            sx={{ flexWrap: "wrap", gap: 0.75 }}
          >
            {DETAILS.map((d) => (
              <ToggleButton
                key={d.value}
                value={d.value}
                sx={pillSx}
                aria-label={`${d.label}: ${d.hint}`}
              >
                <Box sx={{ textAlign: "left" }}>
                  <Typography
                    variant="caption"
                    sx={{ display: "block", fontWeight: 600 }}
                  >
                    {d.label}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{ color: "inherit", opacity: 0.75, fontSize: "0.68rem" }}
                  >
                    {d.hint}
                  </Typography>
                </Box>
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </ScopingQuestion>

        {/* Question 4: Which conditions to include? */}
        <ScopingQuestion label="Which conditions to include?">
          <ToggleButtonGroup
            value={scoping.context_filter}
            exclusive
            onChange={(_, v) =>
              v && onUpdate({ context_filter: v as "current" | "all" })
            }
            size="small"
            sx={{ flexWrap: "wrap", gap: 0.75 }}
          >
            {CONTEXT_OPTIONS.map((c) => (
              <ToggleButton
                key={c.value}
                value={c.value}
                sx={pillSx}
                aria-label={`${c.label}: ${c.hint}`}
              >
                <Box sx={{ textAlign: "left" }}>
                  <Typography
                    variant="caption"
                    sx={{ display: "block", fontWeight: 600 }}
                  >
                    {c.label}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{ color: "inherit", opacity: 0.75, fontSize: "0.68rem" }}
                  >
                    {c.hint}
                  </Typography>
                </Box>
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </ScopingQuestion>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} color="inherit">
          Cancel
        </Button>
        <Button
          onClick={onSubmit}
          variant="contained"
          disableElevation
          sx={{ minWidth: 120 }}
        >
          Run investigation
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ScopingQuestion({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography
        variant="body2"
        sx={{ fontWeight: 600, mb: 1.25, color: "text.primary" }}
      >
        {label}
      </Typography>
      {children}
    </Box>
  );
}

const pillSx = {
  borderRadius: "20px !important",
  border: "1px solid",
  borderColor: "divider",
  px: 2,
  py: 0.75,
  textTransform: "none",
  fontSize: "0.8125rem",
  "&.Mui-selected": {
    bgcolor: "primary.main",
    color: "primary.contrastText",
    "&:hover": { bgcolor: "primary.dark" },
  },
};
