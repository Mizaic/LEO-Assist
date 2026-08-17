/**
 * Atlas trace:
 *   DO: DO-5D885390
 *   DI: DI-693FFEEA
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { color, typography } from "@leo/design-system/tokens";

import { TRIGGER_OPTIONS } from "@/components/pathway/config/triggers";
import {
  EditorAccordionBody,
  EditorAccordionHeader,
  useEditorStripStyle,
} from "./EditorStrip";

export function TriggerContextPanel({
  triggerEvent,
  onTriggerChange,
  planId,
  planDescription,
  onDescriptionChange,
}: {
  triggerEvent: string;
  onTriggerChange: (v: string) => void;
  planId: string;
  planDescription: string;
  onDescriptionChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = TRIGGER_OPTIONS.find((t) => t.id === triggerEvent);
  const strip = useEditorStripStyle();
  return (
    <div style={strip} data-testid="pathway-trigger-strip">
      <EditorAccordionHeader
        title="Pipeline context and trigger"
        open={open}
        onToggle={() => setOpen((v) => !v)}
        icon={<InfoOutlinedIcon fontSize="small" sx={{ color: color.brand.primary }} />}
        trailing={
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              height: 22,
              padding: "0 8px",
              borderRadius: 999,
              border: "1px solid " + color.text.secondary,
              background: color.surface.alt,
              color: color.text.primary,
              fontSize: 11,
              fontWeight: 600,
              fontFamily: typography.fontFamily.body,
            }}
          >
            <PlayArrowIcon sx={{ fontSize: 14 }} />
            {selected?.label || triggerEvent || "No trigger set"}
          </span>
        }
      />
      <EditorAccordionBody open={open}>
        <TriggerFields
          triggerEvent={triggerEvent}
          onTriggerChange={onTriggerChange}
          planId={planId}
          planDescription={planDescription}
          onDescriptionChange={onDescriptionChange}
          selected={selected}
        />
      </EditorAccordionBody>
    </div>
  );
}

function TriggerFields({
  triggerEvent,
  onTriggerChange,
  planId,
  planDescription,
  onDescriptionChange,
  selected,
}: {
  triggerEvent: string;
  onTriggerChange: (v: string) => void;
  planId: string;
  planDescription: string;
  onDescriptionChange: (v: string) => void;
  selected?: (typeof TRIGGER_OPTIONS)[number];
}) {
  return (
    <Stack spacing={2}>
      <Typography variant="body2" sx={{ color: color.text.secondary }}>
        Choose the event that starts this pathway, then describe it in plain English.
      </Typography>
      <FormControl fullWidth size="small">
        <InputLabel>Trigger event</InputLabel>
        <Select
          value={triggerEvent}
          label="Trigger event"
          onChange={(e) => onTriggerChange(e.target.value)}
        >
          {TRIGGER_OPTIONS.map((t) => (
            <MenuItem key={t.id} value={t.id}>
              <Stack>
                <Typography variant="body2">{t.label}</Typography>
                <Typography variant="caption" sx={{ color: color.text.secondary }}>
                  {t.description}
                </Typography>
              </Stack>
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {selected ? (
        <Alert severity="info" icon={false} sx={{ fontSize: "0.8rem" }}>
          <strong>How it works:</strong> {selected.description}
        </Alert>
      ) : null}
      <TextField
        label="Pathway description"
        size="small"
        fullWidth
        multiline
        minRows={2}
        value={planDescription}
        onChange={(e) => onDescriptionChange(e.target.value)}
        helperText="Describe what this pathway does. Shown on the pathways list."
      />
      <RuntimeContextNote triggerEvent={triggerEvent} planId={planId} />
    </Stack>
  );
}

function RuntimeContextNote({
  triggerEvent,
  planId,
}: {
  triggerEvent: string;
  planId: string;
}) {
  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 2,
        border: "1px solid " + color.text.secondary,
        background: color.surface.alt,
      }}
    >
      <Typography variant="caption" fontWeight={600} display="block" gutterBottom>
        Runtime context required
      </Typography>
      <Typography variant="caption" sx={{ color: color.text.secondary }}>
        When this pathway starts, LEO provides patient_id, encounter_id,
        encounter_text, and organization_id.
        {triggerEvent === "training-run-requested" ? " Also training_batch_id." : ""}
        {triggerEvent === "referral-received" ? " Also referral_document." : ""}
        {triggerEvent === "results-received" ? " Also diagnostic_report." : ""}
      </Typography>
      <Box
        sx={{
          mt: 1,
          fontFamily: typography.fontFamily.mono,
          fontSize: "0.7rem",
          background: color.surface.raised,
          p: 1,
          borderRadius: 1,
          overflowX: "auto",
          color: color.text.secondary,
        }}
      >
        POST /fhir/PlanDefinition/{planId}/$apply
        <br />
        {`{ "event_type": "${triggerEvent || "..."}", "patient_id": "..." }`}
      </Box>
    </Box>
  );
}
