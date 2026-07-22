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

const CHIP_SX = { height: 20, fontSize: 10, bgcolor: "#F1F5F9", color: "#334155" };

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
        slotProps={{ paper: { role: "dialog", "aria-labelledby": titleId, sx: { maxWidth: 320, p: 2 } } }}
      >
        <Typography id={titleId} variant="subtitle2" fontWeight={700} sx={{ mb: 0.25 }}>
          {name}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          SNOMED CT {conceptId}
        </Typography>

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
          <Stack component="ul" sx={{ m: 0, p: 0 }} spacing={0.5}>
            {evidence.mentions.map((m) => (
              <MentionRow
                key={m.encounter_id}
                mention={m}
                expanded={evidence.expandedId === m.encounter_id}
                detail={evidence.details[m.encounter_id]}
                detailLoading={evidence.detailLoadingId === m.encounter_id}
                detailError={evidence.detailError}
                onToggle={evidence.toggleDate}
              />
            ))}
          </Stack>
        )}
      </Popover>
    </>
  );
}
