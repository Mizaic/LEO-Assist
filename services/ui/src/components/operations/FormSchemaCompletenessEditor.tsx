/**
 * Completeness groups for a taught form: mandatory, optional, 1-of, n-of, if-then.
 *
 * Atlas trace: UN-3B25A20E
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";

import {
  emptyCompletenessGroup,
  type CompletenessLogicGroup,
} from "./formSchemaTeach";

const KINDS = [
  { value: "mandatory", label: "Mandatory" },
  { value: "optional", label: "Optional" },
  { value: "one_of", label: "1 of these" },
  { value: "n_of", label: "At least N" },
  { value: "if_then", label: "If-then" },
] as const;

interface Props {
  groups: CompletenessLogicGroup[];
  onChange: (groups: CompletenessLogicGroup[]) => void;
}

export function FormSchemaCompletenessEditor({ groups, onChange }: Props) {
  return (
    <Box sx={{ mt: 2 }} data-testid="form-completeness-editor">
      <Typography variant="subtitle2" fontWeight={700}>
        Completeness rules
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        Say what this service must have. Use 1 of these for either/or items such as B1 or B2.
      </Typography>
      <Stack spacing={1.25}>
        {groups.map((group, idx) => (
          <GroupRow
            key={`${group.name}-${idx}`}
            group={group}
            onChange={(next) => onChange(groups.map((item, i) => (i === idx ? next : item)))}
          />
        ))}
      </Stack>
      <Button
        size="small"
        startIcon={<AddIcon />}
        onClick={() => onChange([...groups, emptyCompletenessGroup()])}
        sx={{ mt: 1 }}
      >
        Add completeness rule
      </Button>
    </Box>
  );
}

function GroupRow({
  group,
  onChange,
}: {
  group: CompletenessLogicGroup;
  onChange: (group: CompletenessLogicGroup) => void;
}) {
  const kind = group.kind || (group.required ? "mandatory" : "optional");
  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField
          size="small"
          label="Rule name"
          value={group.name}
          onChange={(e) => onChange({ ...group, name: e.target.value })}
          fullWidth
        />
        <TextField
          size="small"
          select
          label="Rule type"
          value={kind}
          onChange={(e) =>
            onChange({ ...group, kind: e.target.value, required: e.target.value !== "optional" })
          }
          sx={{ minWidth: 160 }}
        >
          {KINDS.map((item) => (
            <MenuItem key={item.value} value={item.value}>
              {item.label}
            </MenuItem>
          ))}
        </TextField>
        {kind === "n_of" ? (
          <TextField
            size="small"
            type="number"
            label="At least"
            value={group.min_count ?? 2}
            onChange={(e) => onChange({ ...group, min_count: Number(e.target.value) || 2 })}
            sx={{ width: 110 }}
            inputProps={{ min: 1, "aria-label": "At least N members" }}
          />
        ) : null}
      </Stack>
      {kind === "one_of" || kind === "n_of" ? (
        <TextField
          size="small"
          label="Options (comma separated)"
          value={(group.members ?? []).map((m) => m.name).join(", ")}
          onChange={(e) => onChange({ ...group, members: namesToMembers(e.target.value) })}
          fullWidth
          sx={{ mt: 1 }}
          helperText="Example: B1, B2"
        />
      ) : null}
      {kind === "if_then" ? (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1 }}>
          <TextField
            size="small"
            label="If this is present"
            value={group.if_group?.name ?? ""}
            onChange={(e) =>
              onChange({ ...group, if_group: { name: e.target.value, kind: "optional", required: false, semantic_categories: [], concept_ids: [] } })
            }
            fullWidth
          />
          <TextField
            size="small"
            label="Then also require"
            value={group.then_group?.name ?? ""}
            onChange={(e) =>
              onChange({ ...group, then_group: { name: e.target.value, kind: "optional", required: false, semantic_categories: [], concept_ids: [] } })
            }
            fullWidth
          />
        </Stack>
      ) : null}
    </Box>
  );
}

function namesToMembers(raw: string): CompletenessLogicGroup[] {
  return raw
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean)
    .map((name) => ({
      name,
      kind: "optional",
      required: false,
      semantic_categories: [],
      concept_ids: [],
    }));
}
