/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E981C7B1
 *   DI: DI-D6E5F94E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E981C7B1")
 */
"use client";

/**
 * Validation Lab A&G thread builder step.
 *
 * Atlas: DI A&G communication_thread (Validation Lab ag case type)
 */

import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

export type AgTurnCategory = "REQUESTER" | "RESPONDER";

export interface AgTurnRow {
  id: string;
  category: AgTurnCategory;
  note: string;
  sentDatetime: string;
  attachmentText: string;
}

interface WizardAgThreadStepsProps {
  agTurnRows: AgTurnRow[];
  agResponseText: string;
  agRequestAttachments: string[];
  onAddTurn: (category: AgTurnCategory) => void;
  onUpdateTurn: (id: string, patch: Partial<AgTurnRow>) => void;
  onRemoveTurn: (id: string) => void;
  onAgResponseTextChange: (value: string) => void;
  onAddRequestAttachment: () => void;
  onUpdateRequestAttachment: (index: number, value: string) => void;
  onRemoveRequestAttachment: (index: number) => void;
}

export function WizardAgThreadStep({
  agTurnRows,
  agResponseText,
  agRequestAttachments,
  onAddTurn,
  onUpdateTurn,
  onRemoveTurn,
  onAgResponseTextChange,
  onAddRequestAttachment,
  onUpdateRequestAttachment,
  onRemoveRequestAttachment,
}: WizardAgThreadStepsProps) {
  return (
    <Stack spacing={2} data-testid="wizard-step-ag-thread">
      <Typography variant="body2" color="text.secondary">
        Build the Advice and Guidance conversation thread. Attachments are
        optional and are stored as document chunks when provided.
      </Typography>
      {agTurnRows.map((row) => (
        <Box
          key={row.id}
          sx={{ border: "1px solid", borderColor: "divider", p: 2, borderRadius: 1 }}
          data-testid={`wizard-ag-turn-${row.id}`}
        >
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} alignItems="center">
              <TextField
                select
                label="Role"
                value={row.category}
                onChange={(e) =>
                  onUpdateTurn(row.id, {
                    category: e.target.value as AgTurnCategory,
                  })
                }
                sx={{ minWidth: 160 }}
                data-testid={`wizard-ag-turn-category-${row.id}`}
              >
                <MenuItem value="REQUESTER">Requester (GP)</MenuItem>
                <MenuItem value="RESPONDER">Responder (specialist)</MenuItem>
              </TextField>
              <IconButton
                aria-label="Remove turn"
                onClick={() => onRemoveTurn(row.id)}
                data-testid={`wizard-ag-turn-remove-${row.id}`}
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Stack>
            <TextField
              label="Message note"
              value={row.note}
              onChange={(e) => onUpdateTurn(row.id, { note: e.target.value })}
              multiline
              minRows={2}
              data-testid={`wizard-ag-turn-note-${row.id}`}
            />
            <TextField
              label="Sent datetime (optional ISO)"
              value={row.sentDatetime}
              onChange={(e) =>
                onUpdateTurn(row.id, { sentDatetime: e.target.value })
              }
              data-testid={`wizard-ag-turn-sent-${row.id}`}
            />
            <TextField
              label="Attachment text (optional)"
              value={row.attachmentText}
              onChange={(e) =>
                onUpdateTurn(row.id, { attachmentText: e.target.value })
              }
              multiline
              minRows={2}
              data-testid={`wizard-ag-turn-attachment-${row.id}`}
            />
          </Stack>
        </Box>
      ))}
      <Stack direction="row" spacing={1}>
        <Button
          startIcon={<AddIcon />}
          onClick={() => onAddTurn("REQUESTER")}
          data-testid="wizard-ag-add-requester"
        >
          Add requester turn
        </Button>
        <Button
          startIcon={<AddIcon />}
          onClick={() => onAddTurn("RESPONDER")}
          data-testid="wizard-ag-add-responder"
        >
          Add responder turn
        </Button>
      </Stack>
      <TextField
        label="Formal A&G response (optional)"
        value={agResponseText}
        onChange={(e) => onAgResponseTextChange(e.target.value)}
        multiline
        minRows={3}
        data-testid="wizard-ag-formal-response"
      />
      <Typography variant="subtitle2">Request-level attachments</Typography>
      {agRequestAttachments.map((text, index) => (
        <Stack direction="row" spacing={1} key={`req-att-${index}`}>
          <TextField
            label={`Request attachment ${index + 1}`}
            value={text}
            onChange={(e) => onUpdateRequestAttachment(index, e.target.value)}
            multiline
            minRows={2}
            fullWidth
            data-testid={`wizard-ag-request-attachment-${index}`}
          />
          <IconButton
            aria-label="Remove request attachment"
            onClick={() => onRemoveRequestAttachment(index)}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Stack>
      ))}
      <Button
        startIcon={<AddIcon />}
        onClick={onAddRequestAttachment}
        data-testid="wizard-ag-add-request-attachment"
      >
        Add request attachment
      </Button>
    </Stack>
  );
}
