"use client";

import { useState } from "react";
import Paper from "@mui/material/Paper";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { TRIGGER_OPTIONS } from "../config/triggers";

export function TriggerContextPanel({
  triggerEvent,
  onTriggerChange,
  planId,
  planDescription,
  onDescriptionChange,
}: {
  triggerEvent: string;
  onTriggerChange: (value: string) => void;
  planId: string;
  planDescription: string;
  onDescriptionChange: (value: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const selected = TRIGGER_OPTIONS.find((t) => t.id === triggerEvent);
  return (
    <Paper variant="outlined" sx={{ mx: 2, mt: 1 }}>
      <Box sx={{ px: 2, py: 1, display: "flex", alignItems: "center", gap: 1, cursor: "pointer" }} onClick={() => setExpanded((e) => !e)}>
        <InfoOutlinedIcon fontSize="small" color="primary" />
        <Typography variant="subtitle2" sx={{ flex: 1 }}>Pipeline Context & Trigger</Typography>
        <Chip size="small" icon={<PlayArrowIcon />} label={selected?.label || triggerEvent || "No trigger set"} color={triggerEvent ? "primary" : "default"} variant="outlined" />
        {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
      </Box>
      {expanded && (
        <Box sx={{ px: 2, pb: 2 }}>
          <Divider sx={{ mb: 2 }} />
          <Stack spacing={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Trigger Event</InputLabel>
              <Select value={triggerEvent} label="Trigger Event" onChange={(e) => onTriggerChange(e.target.value)}>
                {TRIGGER_OPTIONS.map((t) => (
                  <MenuItem key={t.id} value={t.id}>{t.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Pipeline description"
              size="small"
              fullWidth
              multiline
              minRows={2}
              value={planDescription}
              onChange={(e) => onDescriptionChange(e.target.value)}
            />
            <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
              POST /fhir/PlanDefinition/{planId}/$apply {`{ "event_type": "${triggerEvent || "..."}", "patient_id": "..." }`}
            </Typography>
          </Stack>
        </Box>
      )}
    </Paper>
  );
}

