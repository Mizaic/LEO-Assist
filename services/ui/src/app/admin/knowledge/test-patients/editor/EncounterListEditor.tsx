"use client";

/**
 * Editable encounter list -- shared between the NLP, Episodes and
 * Summarisation editors.
 *
 * Each encounter is a small card with:
 *   - free text the AI will read,
 *   - an optional date and source label (clinical surface name),
 *   - a list of expected SNOMED codes (concept_id + term + assertion).
 *
 * Audience standard (UK reading age 11):
 *   - "encounter" -> "note"; "concept_id" -> "SNOMED ID";
 *   - all helper copy is plain English with one idea per sentence.
 *
 * The codes table refuses blank concept ids and keeps the row order
 * stable so the reviewer can see exactly what they typed without
 * the form re-shuffling on every keystroke.
 */

import { useCallback } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import {
  ASSERTION_VALUES,
  type AssertionValue,
  type EditorCode,
  type EditorEncounter,
} from "../types";

interface EncounterListEditorProps {
  encounters: EditorEncounter[];
  showDate?: boolean;
  showSource?: boolean;
  textLabel?: string;
  onChange: (next: EditorEncounter[]) => void;
  disabled?: boolean;
}

const EMPTY_CODE: EditorCode = {
  concept_id: "",
  term: "",
  assertion: "present",
};

function emptyEncounter(): EditorEncounter {
  return {
    id: null,
    source_label: null,
    source_id: null,
    date: null,
    text: "",
    codes: [],
  };
}

function replaceAt<T>(arr: T[], index: number, value: T): T[] {
  const next = arr.slice();
  next[index] = value;
  return next;
}

function removeAt<T>(arr: T[], index: number): T[] {
  const next = arr.slice();
  next.splice(index, 1);
  return next;
}

const ASSERTION_LABEL: Record<AssertionValue, string> = {
  present: "Present",
  absent: "Absent",
  history_of: "History of",
  suspected: "Suspected",
  uncertain: "Uncertain",
};

// LONG FUNCTION: shared editor that owns encounter + code state.
// Splitting further would scatter the controlled-input plumbing.
export default function EncounterListEditor({
  encounters,
  showDate = false,
  showSource = false,
  textLabel = "Note text",
  onChange,
  disabled = false,
}: EncounterListEditorProps) {
  const updateEncounter = useCallback(
    (index: number, patch: Partial<EditorEncounter>) => {
      onChange(
        replaceAt(encounters, index, { ...encounters[index], ...patch }),
      );
    },
    [encounters, onChange],
  );

  const addEncounter = useCallback(() => {
    onChange([...encounters, emptyEncounter()]);
  }, [encounters, onChange]);

  const removeEncounter = useCallback(
    (index: number) => {
      onChange(removeAt(encounters, index));
    },
    [encounters, onChange],
  );

  const updateCode = useCallback(
    (encIndex: number, codeIndex: number, patch: Partial<EditorCode>) => {
      const enc = encounters[encIndex];
      const codes = replaceAt(enc.codes, codeIndex, {
        ...enc.codes[codeIndex],
        ...patch,
      });
      updateEncounter(encIndex, { codes });
    },
    [encounters, updateEncounter],
  );

  const addCode = useCallback(
    (encIndex: number) => {
      const enc = encounters[encIndex];
      updateEncounter(encIndex, { codes: [...enc.codes, { ...EMPTY_CODE }] });
    },
    [encounters, updateEncounter],
  );

  const removeCode = useCallback(
    (encIndex: number, codeIndex: number) => {
      const enc = encounters[encIndex];
      updateEncounter(encIndex, { codes: removeAt(enc.codes, codeIndex) });
    },
    [encounters, updateEncounter],
  );

  return (
    <Stack spacing={2} data-testid="encounter-list-editor">
      {encounters.length === 0 ? (
        <Box
          sx={{
            p: 2,
            border: "1px dashed",
            borderColor: "divider",
            borderRadius: 1,
            textAlign: "center",
          }}
        >
          <Typography variant="body2" color="text.secondary">
            No notes yet. Add one to give the AI something to read.
          </Typography>
        </Box>
      ) : (
        encounters.map((enc, index) => (
          <Box
            key={`enc-${index}`}
            sx={{
              p: 2,
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              display: "flex",
              flexDirection: "column",
              gap: 1.5,
            }}
            data-testid={`encounter-row-${index}`}
          >
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <Typography variant="subtitle2">Note {index + 1}</Typography>
              <Tooltip title="Remove this note" arrow>
                <span>
                  <IconButton
                    size="small"
                    aria-label={`Remove note ${index + 1}`}
                    onClick={() => removeEncounter(index)}
                    disabled={disabled}
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            </Box>

            <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
              {showDate ? (
                <TextField
                  label="Date"
                  type="date"
                  size="small"
                  value={enc.date ?? ""}
                  onChange={(event) =>
                    updateEncounter(index, {
                      date: event.target.value || null,
                    })
                  }
                  InputLabelProps={{ shrink: true }}
                  disabled={disabled}
                  sx={{ minWidth: 160 }}
                />
              ) : null}
              {showSource ? (
                <>
                  <TextField
                    label="Source label"
                    placeholder="e.g. Encounter / Referral"
                    size="small"
                    value={enc.source_label ?? ""}
                    onChange={(event) =>
                      updateEncounter(index, {
                        source_label: event.target.value || null,
                      })
                    }
                    disabled={disabled}
                    sx={{ minWidth: 200 }}
                  />
                  <TextField
                    label="Source ID"
                    placeholder="optional"
                    size="small"
                    value={enc.source_id ?? ""}
                    onChange={(event) =>
                      updateEncounter(index, {
                        source_id: event.target.value || null,
                      })
                    }
                    disabled={disabled}
                    sx={{ minWidth: 200 }}
                  />
                </>
              ) : null}
            </Box>

            <TextField
              label={textLabel}
              multiline
              minRows={3}
              value={enc.text}
              onChange={(event) =>
                updateEncounter(index, { text: event.target.value })
              }
              disabled={disabled}
              fullWidth
            />

            <Divider />

            <Box>
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  mb: 1,
                }}
              >
                <Typography variant="subtitle2">Expected SNOMED codes</Typography>
                <Chip
                  size="small"
                  label={`${enc.codes.length} code(s)`}
                  variant="outlined"
                />
              </Box>
              <Stack spacing={1} data-testid={`code-list-${index}`}>
                {enc.codes.map((code, codeIndex) => (
                  <Box
                    key={`code-${index}-${codeIndex}`}
                    sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}
                  >
                    <TextField
                      label="SNOMED ID"
                      size="small"
                      value={code.concept_id}
                      onChange={(event) =>
                        updateCode(index, codeIndex, {
                          concept_id: event.target.value.trim(),
                        })
                      }
                      disabled={disabled}
                      sx={{ minWidth: 160 }}
                      required
                    />
                    <TextField
                      label="Term (optional)"
                      size="small"
                      value={code.term ?? ""}
                      onChange={(event) =>
                        updateCode(index, codeIndex, {
                          term: event.target.value,
                        })
                      }
                      disabled={disabled}
                      sx={{ flex: 1, minWidth: 200 }}
                    />
                    <TextField
                      select
                      label="Assertion"
                      size="small"
                      value={code.assertion}
                      onChange={(event) =>
                        updateCode(index, codeIndex, {
                          assertion: event.target.value as AssertionValue,
                        })
                      }
                      disabled={disabled}
                      sx={{ minWidth: 140 }}
                    >
                      {ASSERTION_VALUES.map((value) => (
                        <MenuItem key={value} value={value}>
                          {ASSERTION_LABEL[value]}
                        </MenuItem>
                      ))}
                    </TextField>
                    <IconButton
                      size="small"
                      aria-label={`Remove code ${codeIndex + 1} from note ${index + 1}`}
                      onClick={() => removeCode(index, codeIndex)}
                      disabled={disabled}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </Box>
                ))}
                <Button
                  size="small"
                  startIcon={<AddIcon />}
                  onClick={() => addCode(index)}
                  disabled={disabled}
                  sx={{ alignSelf: "flex-start" }}
                >
                  Add code
                </Button>
              </Stack>
            </Box>
          </Box>
        ))
      )}

      <Button
        variant="outlined"
        startIcon={<AddIcon />}
        onClick={addEncounter}
        disabled={disabled}
        sx={{ alignSelf: "flex-start" }}
      >
        Add note
      </Button>
    </Stack>
  );
}
