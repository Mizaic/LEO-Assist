"use client";

/**
 * Wizard step 2 (build profile / PMH) and step 3 (encounters) for
 * CreatePatientWizard. Both are optional -- a reviewer can skip
 * straight to the referral step.
 *
 * Atlas: DI-724CD8A5
 */

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";

import SnomedConceptPicker from "./SnomedConceptPicker";
import type { PmhCategory } from "./labApi";
import type { EncounterRow, PmhRow } from "./useCreatePatientWizard";

const PMH_CATEGORY_LABEL: Record<PmhCategory, string> = {
  condition: "Condition",
  medication: "Medication",
  allergy: "Allergy",
};

interface PmhStepProps {
  rows: PmhRow[];
  onAdd: (category: PmhCategory) => void;
  onUpdate: (id: string, patch: Partial<PmhRow>) => void;
  onRemove: (id: string) => void;
}

export function ProfilePmhStep({ rows, onAdd, onUpdate, onRemove }: PmhStepProps) {
  return (
    <Stack spacing={2} data-testid="wizard-step-profile">
      <Typography variant="body2" color="text.secondary">
        Optional. Pick past medical history, medications, and allergies from
        real SNOMED terms. These are folded into the referral narrative below
        so extraction is exercised exactly like a real referral -- never
        bypassed.
      </Typography>
      {rows.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          No past medical history added yet.
        </Typography>
      )}
      {rows.map((row) => (
        <Stack
          key={row.id}
          direction="row"
          spacing={1}
          alignItems="flex-start"
          data-testid={`wizard-pmh-row-${row.id}`}
        >
          <TextField
            select
            size="small"
            label="Category"
            value={row.category}
            onChange={(e) =>
              onUpdate(row.id, { category: e.target.value as PmhCategory })
            }
            sx={{ minWidth: 160 }}
          >
            {Object.entries(PMH_CATEGORY_LABEL).map(([value, label]) => (
              <MenuItem key={value} value={value}>
                {label}
              </MenuItem>
            ))}
          </TextField>
          <SnomedConceptPicker
            conceptId={row.conceptId}
            term={row.term}
            testIdSuffix={row.id}
            onChange={({ conceptId, term }) =>
              onUpdate(row.id, { conceptId, term })
            }
          />
          <IconButton
            aria-label="Remove past medical history entry"
            onClick={() => onRemove(row.id)}
            size="small"
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Stack>
      ))}
      <Stack direction="row" spacing={1} flexWrap="wrap">
        {(Object.keys(PMH_CATEGORY_LABEL) as PmhCategory[]).map((category) => (
          <Button
            key={category}
            size="small"
            variant="outlined"
            onClick={() => onAdd(category)}
            data-testid={`wizard-add-pmh-${category}`}
          >
            Add {PMH_CATEGORY_LABEL[category].toLowerCase()}
          </Button>
        ))}
      </Stack>
    </Stack>
  );
}

interface EncounterStepProps {
  rows: EncounterRow[];
  onAdd: () => void;
  onUpdate: (id: string, patch: Partial<EncounterRow>) => void;
  onRemove: (id: string) => void;
}

export function EncountersStep({ rows, onAdd, onUpdate, onRemove }: EncounterStepProps) {
  return (
    <Stack spacing={2} data-testid="wizard-step-encounters">
      <Typography variant="body2" color="text.secondary">
        Optional. Add prior encounter notes for background context. These are
        stored on the patient but are not sent to the pipeline -- only the
        referral (next step) is submitted for extraction, matching the real
        production contract.
      </Typography>
      {rows.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          No background encounters added yet.
        </Typography>
      )}
      {rows.map((row) => (
        <Box
          key={row.id}
          sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1.5 }}
          data-testid={`wizard-encounter-row-${row.id}`}
        >
          <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
            <TextField
              size="small"
              label="Label"
              value={row.label}
              onChange={(e) => onUpdate(row.id, { label: e.target.value })}
              sx={{ flex: 1 }}
            />
            <TextField
              size="small"
              label="Date"
              type="date"
              value={row.date}
              onChange={(e) => onUpdate(row.id, { date: e.target.value })}
              InputLabelProps={{ shrink: true }}
            />
            <IconButton
              aria-label="Remove encounter"
              onClick={() => onRemove(row.id)}
              size="small"
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Stack>
          <TextField
            fullWidth
            multiline
            minRows={3}
            label="Encounter note"
            value={row.text}
            onChange={(e) => onUpdate(row.id, { text: e.target.value })}
            data-testid={`wizard-encounter-text-${row.id}`}
          />
        </Box>
      ))}
      <Button
        size="small"
        variant="outlined"
        onClick={onAdd}
        data-testid="wizard-add-encounter"
        sx={{ alignSelf: "flex-start" }}
      >
        Add encounter
      </Button>
    </Stack>
  );
}
