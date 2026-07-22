/**
 * A problem-list chip that reveals its SNOMED CT code, preferred term, and
 * dated evidence on selection. Dates load first (lightweight); the
 * evidence sentence for a given date loads only once that date is
 * expanded, so opening the chip never dumps a wall of clinical text.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-7DE8E8ED
 */
"use client";

import { useId, useRef, useState } from "react";
import Chip from "@mui/material/Chip";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import { MentionRow } from "./MentionRow";
import { useConceptEvidence } from "./useConceptEvidence";

const CHIP_SX = {
  height: 20,
  fontSize: 10,
  fontWeight: 600,
  bgcolor: "#F1F5F9",
  color: "#334155",
  border: "1px solid transparent",
  transition: "background-color 120ms ease, border-color 120ms ease",
  "&:hover": { bgcolor: "#E2E8F0", borderColor: "#CBD5E1" },
  "&:focus-visible": { outline: "2px solid #2563EB", outlineOffset: "1px" },
};

interface CodedEntityChipProps {
  patientId: string;
  name: string;
  conceptId: string | null;
}

export function CodedEntityChip({ patientId, name, conceptId }: CodedEntityChipProps) {
  const titleId = useId();
  const anchorRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const evidence = useConceptEvidence(patientId, conceptId);

  if (!conceptId) {
    return <Chip label={name} size="small" sx={CHIP_SX} />;
  }

  const handleOpen = () => {
    setOpen(true);
    void evidence.loadMentions();
  };

  return (
    <>
      <Chip
        ref={anchorRef}
        label={name}
        size="small"
        clickable
        onClick={handleOpen}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`${name}. View SNOMED code and evidence.`}
        sx={CHIP_SX}
      />
      <Popover
        open={open}
        anchorEl={anchorRef.current}
        onClose={() => setOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        slotProps={{
          paper: {
            role: "dialog",
            "aria-labelledby": titleId,
            sx: {
              maxWidth: 340,
              minWidth: 280,
              p: 2,
              borderRadius: 2,
              boxShadow: "0 8px 24px rgba(15, 23, 42, 0.14)",
            },
          },
        }}
      >
        <Typography id={titleId} variant="subtitle2" fontWeight={700} sx={{ mb: 0.5 }}>
          {name}
        </Typography>
        <Chip
          label={`SNOMED CT ${conceptId}`}
          size="small"
          sx={{
            height: 20,
            fontSize: "0.6875rem",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontWeight: 600,
            bgcolor: "#EEF2FF",
            color: "#4338CA",
            mb: 1.25,
            "& .MuiChip-label": { px: 0.8 },
          }}
        />

        {evidence.mentionsLoading && (
          <Stack direction="row" spacing={1} alignItems="center" sx={{ py: 1 }}>
            <CircularProgress size={14} aria-label="Loading" role="status" />
            <Typography variant="caption" color="text.secondary">
              Loading dates...
            </Typography>
          </Stack>
        )}

        {evidence.mentionsError && (
          <Alert severity="error" sx={{ fontSize: 11, py: 0.25 }}>
            {evidence.mentionsError}
          </Alert>
        )}

        {evidence.mentions !== null && evidence.mentions.length === 0 && (
          <Typography variant="caption" color="text.secondary" fontStyle="italic">
            No recorded mentions found.
          </Typography>
        )}

        {evidence.mentions !== null && evidence.mentions.length > 0 && (
          <Stack component="ul" sx={{ m: 0, p: 0 }} spacing={0.75}>
            {evidence.mentions.map((m) => {
              const key = evidence.mentionKey(m.source_type, m.source_id);
              return (
                <MentionRow
                  key={key}
                  mention={m}
                  expanded={evidence.expandedKey === key}
                  detail={evidence.details[key]}
                  detailLoading={evidence.detailLoadingKey === key}
                  detailError={evidence.detailError}
                  onToggle={evidence.toggleMention}
                />
              );
            })}
          </Stack>
        )}
      </Popover>
    </>
  );
}
