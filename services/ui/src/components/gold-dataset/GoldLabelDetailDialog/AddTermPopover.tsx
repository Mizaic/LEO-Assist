/**
 * AddTermPopover -- Wave E Phase 2a-iv
 *
 * Replaces the always-visible "Add a missing term" form that
 * previously sat between the Terms list and the metadata footer.
 * Now triggered from a single "Add term" button in the Terms
 * toolbar, using the same surface tone as other knowledge popovers.
 *
 * Behaviour preserved:
 *   - Sentence-text-selection still pre-fills the term field via
 *     the parent's setNewEntityText() (the parent passes the
 *     current value down so the popover stays in sync).
 *   - Enter submits when the field is non-empty.
 *   - The parent owns the entity-add handler and any dedupe checks.
 *
 * Atlas trace:
 *   DO: DO-1E9BCC70
 *   DI: DI-3035F221
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-1E9BCC70")
 */
"use client";

import { useEffect, useRef } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  VALID_ENTITY_SEMANTIC_LABELS as ENTITY_LABEL_OPTIONS,
  type EntitySemanticLabel,
} from "@/lib/entitySemanticLabels";

import { ASSERTION_OPTIONS, formatAssertion } from "../goldDatasetUtils";

interface AddTermPopoverProps {
  open: boolean;
  anchorEl: HTMLElement | null;
  newEntityText: string;
  newEntityLabel: EntitySemanticLabel;
  newEntityAssertion: (typeof ASSERTION_OPTIONS)[number];
  saving: boolean;
  selectionAdded: boolean;
  onClose: () => void;
  onTextChange: (value: string) => void;
  onLabelChange: (value: EntitySemanticLabel) => void;
  onAssertionChange: (value: (typeof ASSERTION_OPTIONS)[number]) => void;
  onSubmit: () => void;
  inputRef?: React.Ref<HTMLInputElement>;
}

export default function AddTermPopover(props: AddTermPopoverProps) {
  const {
    open,
    anchorEl,
    newEntityText,
    newEntityLabel,
    newEntityAssertion,
    saving,
    selectionAdded,
    onClose,
    onTextChange,
    onLabelChange,
    onAssertionChange,
    onSubmit,
    inputRef,
  } = props;

  const localRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const handle = setTimeout(() => {
      localRef.current?.focus();
    }, 60);
    return () => clearTimeout(handle);
  }, [open]);

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      transformOrigin={{ vertical: "top", horizontal: "right" }}
      slotProps={{
        paper: {
          sx: {
            mt: 1,
            p: 2,
            width: 380,
            borderRadius: 2,
            border: "1px solid",
            borderColor: "divider",
            boxShadow: "0 12px 28px rgba(15, 23, 42, 0.12)",
          },
        },
      }}
      data-testid="add-term-popover"
    >
      <Typography
        sx={{
          fontSize: "0.75rem",
          fontWeight: 600,
          color: "text.primary",
          mb: 1,
        }}
      >
        Add a missing term
      </Typography>
      <Stack spacing={1}>
        <TextField
          size="small"
          autoFocus
          value={newEntityText}
          onChange={(event) => onTextChange(event.target.value)}
          placeholder="Type or highlight text in the sentence"
          disabled={saving}
          inputRef={(node: HTMLInputElement | null) => {
            localRef.current = node;
            if (typeof inputRef === "function") inputRef(node);
            else if (inputRef && "current" in inputRef) {
              (inputRef as React.MutableRefObject<HTMLInputElement | null>).current = node;
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && newEntityText.trim()) {
              event.preventDefault();
              onSubmit();
            }
          }}
          sx={{
            "& .MuiInputBase-input": { py: 0.6, fontSize: "0.85rem" },
            "& .MuiOutlinedInput-root": selectionAdded
              ? { "& fieldset": { borderColor: "success.main" } }
              : {},
          }}
          data-testid="add-term-text-input"
        />
        <Stack direction="row" spacing={1}>
          <TextField
            select
            size="small"
            value={newEntityLabel}
            onChange={(event) => onLabelChange(event.target.value as EntitySemanticLabel)}
            disabled={saving}
            sx={{
              flex: 1,
              "& .MuiInputBase-input": { py: 0.6, fontSize: "0.78rem" },
            }}
            data-testid="add-term-type-select"
          >
            {ENTITY_LABEL_OPTIONS.map((option) => (
              <MenuItem key={option} value={option}>
                {option}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            value={newEntityAssertion}
            onChange={(event) =>
              onAssertionChange(
                event.target.value as (typeof ASSERTION_OPTIONS)[number],
              )
            }
            disabled={saving}
            sx={{
              flex: 1,
              "& .MuiInputBase-input": { py: 0.6, fontSize: "0.78rem" },
            }}
            data-testid="add-term-assertion-select"
          >
            {ASSERTION_OPTIONS.map((option) => (
              <MenuItem key={option} value={option}>
                {formatAssertion(option)}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
        <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end" }}>
          <Button
            size="small"
            variant="text"
            onClick={onClose}
            disabled={saving}
            sx={{ textTransform: "none", color: "text.secondary" }}
          >
            Cancel
          </Button>
          <Button
            size="small"
            variant="contained"
            onClick={onSubmit}
            disabled={saving || !newEntityText.trim()}
            data-testid="add-term-submit"
            sx={{ textTransform: "none", boxShadow: "none" }}
          >
            Add term
          </Button>
        </Box>
      </Stack>
    </Popover>
  );
}
