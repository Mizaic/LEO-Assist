"use client";

import { useState } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import HowToVoteOutlinedIcon from "@mui/icons-material/HowToVoteOutlined";
import CodeIcon from "@mui/icons-material/Code";
import { AnchorReviewRecord, DomainChip } from "./AnchorReviewPanel";

// ---------------------------------------------------------------------------
// Domain options for the "Neither" picker
// ---------------------------------------------------------------------------

const ALL_DOMAINS = [
  "CANCER_DIAGNOSIS",
  "CANCER_DIAGNOSIS_EXCLUDED",
  "2WW_REFERRAL",
  "2WW_CLINIC_SEEN",
  "2WW_REFERRAL_REJECTED",
  "CANCER_TREATMENT",
  "CANCER_TREATMENT_HISTORICAL",
  "INVESTIGATION",
  "METASTATIC_DISEASE",
  "NON_CANCER",
  "AMBIGUOUS",
] as const;

// ---------------------------------------------------------------------------
// Milestone colour
// ---------------------------------------------------------------------------

const MILESTONE_COLORS: Record<
  string,
  "default" | "primary" | "secondary" | "info" | "success" | "warning" | "error"
> = {
  referral: "primary",
  diagnosis: "error",
  treatment_start: "secondary",
  specialist_visit: "info",
};

// ---------------------------------------------------------------------------
// Card component
// ---------------------------------------------------------------------------

interface Props {
  record: AnchorReviewRecord;
  submitting: boolean;
  onVote: (domain: string, note: string) => void;
}

export default function AnchorReviewCard({ record, submitting, onVote }: Props) {
  const [neitherOpen, setNeitherOpen] = useState(false);
  const [neitherDomain, setNeitherDomain] = useState<string>("");
  const [neitherNote, setNeitherNote] = useState("");
  const [rulesOpen, setRulesOpen] = useState(false);

  const milestoneColor = MILESTONE_COLORS[record.milestone_type] ?? "default";

  const btnSx = {
    textTransform: "none",
    fontWeight: 600,
    px: 2,
    py: 0.75,
    borderRadius: 2,
    fontSize: "0.82rem",
  } as const;

  function handleQuickVote(domain: string) {
    onVote(domain, "");
  }

  function handleNeitherSubmit() {
    if (!neitherDomain) return;
    onVote(neitherDomain, neitherNote);
  }

  const conceptWrong =
    !record.model_a_concept_correct || !record.model_b_concept_correct;

  return (
    <Card
      variant="outlined"
      sx={{
        borderColor: record.non_cancer_flag ? "error.main" : "warning.main",
        borderWidth: 1.5,
      }}
    >
      <CardContent>
        {/* Header row */}
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          justifyContent="space-between"
          sx={{ mb: 1.5 }}
        >
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Chip
              label={record.milestone_type.replace(/_/g, " ")}
              color={milestoneColor}
              size="small"
              sx={{ fontWeight: 700 }}
            />
            {record.non_cancer_flag && (
              <Chip
                icon={<WarningAmberIcon />}
                label="NON_CANCER"
                color="error"
                size="small"
                sx={{ fontWeight: 700 }}
              />
            )}
            {record.original_label === 1 && (
              <Chip
                label="was label=1"
                size="small"
                variant="outlined"
                color="default"
                sx={{ fontSize: "0.7rem" }}
              />
            )}
            {conceptWrong && (
              <Chip
                label="concept mismatch"
                size="small"
                color="warning"
                variant="outlined"
                sx={{ fontSize: "0.7rem" }}
              />
            )}
            {record.patient_id && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ fontFamily: "var(--font-mono)" }}
              >
                Patient {record.patient_id}
              </Typography>
            )}
          </Stack>

          {/* Model predictions */}
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Tooltip title="Claude Haiku said:">
              <Box>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mr: 0.5 }}
                >
                  Haiku:
                </Typography>
                <DomainChip domain={record.model_a_domain} />
              </Box>
            </Tooltip>
            <Typography variant="caption" color="text.secondary">
              vs
            </Typography>
            <Tooltip title="GPT-5-mini said:">
              <Box>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mr: 0.5 }}
                >
                  GPT:
                </Typography>
                <DomainChip domain={record.model_b_domain} />
              </Box>
            </Tooltip>
          </Stack>
        </Stack>

        {/* Original concept */}
        {record.original_concept_id && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 0.5, fontFamily: "var(--font-mono)" }}
          >
            SNOMED: {record.original_concept_id}
          </Typography>
        )}

        {/* Evidence text */}
        <Box
          sx={{
            p: 1.5,
            bgcolor: "action.hover",
            borderRadius: 1,
            mb: 1.5,
            fontFamily: "var(--font-mono)",
            fontSize: "0.82rem",
            lineHeight: 1.6,
            color: "text.primary",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {record.text || "(no text)"}
        </Box>

        {/* Rationales */}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 1.5 }}>
          {record.model_a_rationale && (
            <Box sx={{ flex: 1 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ fontWeight: 600 }}
              >
                Haiku rationale:
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", fontStyle: "italic" }}
              >
                {record.model_a_rationale}
              </Typography>
            </Box>
          )}
          {record.model_b_rationale && (
            <Box sx={{ flex: 1 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ fontWeight: 600 }}
              >
                GPT rationale:
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", fontStyle: "italic" }}
              >
                {record.model_b_rationale}
              </Typography>
            </Box>
          )}
        </Stack>

        {/* TargetRules (collapsible) */}
        {(record.model_a_target_rule || record.model_b_target_rule) && (
          <Box sx={{ mb: 1.5 }}>
            <Button
              size="small"
              startIcon={<CodeIcon sx={{ fontSize: 14 }} />}
              endIcon={
                <ExpandMoreIcon
                  sx={{
                    fontSize: 14,
                    transform: rulesOpen ? "rotate(180deg)" : "none",
                    transition: "transform 0.2s",
                  }}
                />
              }
              onClick={() => setRulesOpen((o) => !o)}
              sx={{
                textTransform: "none",
                fontSize: "0.75rem",
                color: "text.secondary",
                p: 0,
              }}
            >
              TargetRules
            </Button>
            <Collapse in={rulesOpen} unmountOnExit>
              <Stack spacing={0.5} sx={{ mt: 1 }}>
                {record.model_a_target_rule && (
                  <Box
                    component="pre"
                    sx={{
                      fontSize: "0.7rem",
                      fontFamily: "var(--font-mono)",
                      bgcolor: "action.selected",
                      p: 1,
                      borderRadius: 1,
                      overflowX: "auto",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-all",
                      m: 0,
                    }}
                  >
                    Haiku: {record.model_a_target_rule}
                  </Box>
                )}
                {record.model_b_target_rule && (
                  <Box
                    component="pre"
                    sx={{
                      fontSize: "0.7rem",
                      fontFamily: "var(--font-mono)",
                      bgcolor: "action.selected",
                      p: 1,
                      borderRadius: 1,
                      overflowX: "auto",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-all",
                      m: 0,
                    }}
                  >
                    GPT: {record.model_b_target_rule}
                  </Box>
                )}
              </Stack>
            </Collapse>
          </Box>
        )}

        <Divider sx={{ mb: 1.5 }} />

        {/* Quick-vote row */}
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ mr: 0.5 }}
          >
            Correct domain:
          </Typography>
          <Tooltip
            title={`Haiku was right — ${record.model_a_domain}`}
          >
            <span>
              <Button
                variant="contained"
                color="primary"
                size="small"
                disabled={submitting}
                onClick={() => handleQuickVote(record.model_a_domain)}
                sx={btnSx}
              >
                {submitting ? (
                  <CircularProgress size={14} />
                ) : (
                  `Haiku · ${record.model_a_domain.replace(/_/g, " ")}`
                )}
              </Button>
            </span>
          </Tooltip>
          <Tooltip
            title={`GPT-5-mini was right — ${record.model_b_domain}`}
          >
            <span>
              <Button
                variant="contained"
                color="secondary"
                size="small"
                disabled={submitting}
                onClick={() => handleQuickVote(record.model_b_domain)}
                sx={btnSx}
              >
                {submitting ? (
                  <CircularProgress size={14} />
                ) : (
                  `GPT · ${record.model_b_domain.replace(/_/g, " ")}`
                )}
              </Button>
            </span>
          </Tooltip>
          <Tooltip title="Neither model was right — choose the correct domain">
            <Button
              variant="outlined"
              color="inherit"
              size="small"
              disabled={submitting}
              onClick={() => setNeitherOpen((o) => !o)}
              endIcon={
                <ExpandMoreIcon
                  sx={{
                    transform: neitherOpen ? "rotate(180deg)" : "none",
                    transition: "transform 0.2s",
                  }}
                />
              }
              sx={{ ...btnSx, borderColor: "divider" }}
            >
              Neither
            </Button>
          </Tooltip>
        </Stack>

        {/* Neither — inline domain picker */}
        <Collapse in={neitherOpen} unmountOnExit>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={2}
            alignItems={{ sm: "flex-end" }}
            sx={{
              mt: 2,
              pt: 2,
              borderTop: "1px solid",
              borderColor: "divider",
            }}
          >
            <Select
              value={neitherDomain}
              onChange={(e) => setNeitherDomain(e.target.value)}
              displayEmpty
              size="small"
              sx={{ minWidth: 240 }}
            >
              <MenuItem value="" disabled>
                Choose correct domain
              </MenuItem>
              {ALL_DOMAINS.map((d) => (
                <MenuItem key={d} value={d}>
                  {d.replace(/_/g, " ")}
                </MenuItem>
              ))}
            </Select>
            <TextField
              label="Notes (optional)"
              value={neitherNote}
              onChange={(e) => setNeitherNote(e.target.value)}
              size="small"
              sx={{ flex: 1 }}
              placeholder="e.g. this is a referral letter, not a clinic attendance"
            />
            <Button
              variant="contained"
              color="primary"
              size="small"
              onClick={handleNeitherSubmit}
              disabled={!neitherDomain || submitting}
              startIcon={
                submitting ? (
                  <CircularProgress size={14} />
                ) : (
                  <HowToVoteOutlinedIcon />
                )
              }
              sx={{ whiteSpace: "nowrap" }}
            >
              Submit
            </Button>
          </Stack>
        </Collapse>
      </CardContent>
    </Card>
  );
}
