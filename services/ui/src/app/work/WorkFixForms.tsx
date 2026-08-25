/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59, DI-6BD7B681
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */
"use client";

import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import TermSearch from "@/components/TermSearch";
import type { TermSearchResult } from "@/lib/types";
import { TeachMode } from "./WorkTeachForm";
import {
  saveContextCue,
  savePhraseMapping,
  saveSuppressRule,
  type WorkFixKind,
} from "./workFixApi";

const CONTEXT_CATEGORIES = [
  { value: "NEGATED_EXISTENCE", label: "Not present" },
  { value: "HISTORICAL", label: "In the past" },
  { value: "FAMILY", label: "Family history" },
  { value: "HYPOTHETICAL", label: "Possible or planned" },
];

const CONTEXT_DIRECTIONS = [
  { value: "FORWARD", label: "After the phrase" },
  { value: "BACKWARD", label: "Before the phrase" },
  { value: "BIDIRECTIONAL", label: "Both sides" },
];

interface ActiveFixFormProps {
  mode: WorkFixKind | "idle";
  phrase: string;
  entityText: string;
  entityLabel?: string;
  reviewId?: string | null;
  encounterText?: string;
  contextPhrase: string;
  category: string;
  direction: string;
  busy: boolean;
  onContextPhraseChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  onDirectionChange: (value: string) => void;
  onIdle: () => void;
  onRunFix: (kind: WorkFixKind, action: () => Promise<void>) => Promise<void>;
}

export function ActiveFixForm(props: ActiveFixFormProps) {
  const { mode } = props;
  if (mode === "map") return <MapForm {...props} />;
  if (mode === "exclude") return <ExcludeMode {...props} />;
  if (mode === "context") return <ContextMode {...props} />;
  if (mode === "teach") return <TeachMode {...props} />;
  return null;
}

function MapForm({
  phrase,
  entityText,
  entityLabel,
  encounterText,
  onIdle,
  onRunFix,
}: ActiveFixFormProps) {
  return (
    <TermSearch
      initialQuery={phrase || entityText}
      entityText={phrase || entityText}
      entityLabel={entityLabel ?? ""}
      initialEvidence={encounterText}
      confirmLabel="Save draft"
      title="Map this phrase"
      onSelect={(result: TermSearchResult) =>
        void onRunFix("map", () =>
          savePhraseMapping(
            phrase || entityText,
            result.snomed_concept_id,
            result.term,
          ),
        )
      }
      onClose={onIdle}
      onCorrection={() => undefined}
    />
  );
}

function ExcludeMode({
  phrase,
  entityText,
  entityLabel,
  reviewId,
  contextPhrase,
  busy,
  onContextPhraseChange,
  onIdle,
  onRunFix,
}: ActiveFixFormProps) {
  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.secondary">
        This saves an exclude draft. It is not live until a different person publishes.
      </Typography>
      <TextField
        size="small"
        label="Nearby words (optional)"
        value={contextPhrase}
        onChange={(event) => onContextPhraseChange(event.target.value)}
      />
      <Stack direction="row" spacing={1}>
        <Button
          size="small"
          variant="contained"
          color="warning"
          disabled={busy}
          onClick={() =>
            void onRunFix("exclude", () =>
              saveSuppressRule({
                entityText: phrase || entityText,
                entityLabel,
                contextPhrase,
                reviewId,
              }),
            )
          }
        >
          {busy ? "Saving..." : "Do not code this"}
        </Button>
        <Button size="small" onClick={onIdle} disabled={busy}>
          Cancel
        </Button>
      </Stack>
    </Stack>
  );
}

function ContextMode({
  phrase,
  entityText,
  category,
  direction,
  busy,
  onCategoryChange,
  onDirectionChange,
  onIdle,
  onRunFix,
}: ActiveFixFormProps) {
  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.secondary">
        A context cue goes live now. Use it only for nearby words, not a new code.
      </Typography>
      <TextField
        select
        size="small"
        label="Meaning"
        value={category}
        onChange={(event) => onCategoryChange(event.target.value)}
      >
        {CONTEXT_CATEGORIES.map((option) => (
          <MenuItem key={option.value} value={option.value}>
            {option.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        size="small"
        label="Look where"
        value={direction}
        onChange={(event) => onDirectionChange(event.target.value)}
      >
        {CONTEXT_DIRECTIONS.map((option) => (
          <MenuItem key={option.value} value={option.value}>
            {option.label}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={1}>
        <Button
          size="small"
          variant="contained"
          disabled={busy}
          onClick={() =>
            void onRunFix("context", () =>
              saveContextCue({
                literal: phrase || entityText,
                category,
                direction,
              }),
            )
          }
        >
          {busy ? "Saving..." : "Save cue"}
        </Button>
        <Button size="small" onClick={onIdle} disabled={busy}>
          Cancel
        </Button>
      </Stack>
    </Stack>
  );
}
