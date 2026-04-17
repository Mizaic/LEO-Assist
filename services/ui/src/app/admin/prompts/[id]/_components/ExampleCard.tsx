"use client";

/**
 * One row in the few-shot examples library. Extracted from
 * prompts/[id]/page.tsx (Phase 4b decomposition).
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import VisibilityIcon from "@mui/icons-material/Visibility";

import { InputDisplay } from "./InputDisplay";
import { OutputPreview } from "./OutputPreview";
import {
  CATEGORY_OPTIONS,
  SCOPE_OPTIONS,
  categoryColor,
  categoryLabel,
  type FewShotExample,
} from "./types";

interface ExampleCardProps {
  ex: FewShotExample;
  idx: number;
  onChange: (
    id: string,
    field: keyof FewShotExample,
    value: string | boolean,
  ) => void;
  onRemove: (id: string) => void;
  startInEdit?: boolean;
}

export function ExampleCard({
  ex,
  idx,
  onChange,
  onRemove,
  startInEdit = false,
}: ExampleCardProps) {
  const [editing, setEditing] = useState(startInEdit);

  return (
    <Card variant="outlined" sx={{ mb: 1.5, borderRadius: 2 }}>
      <CardContent sx={{ pb: "12px !important" }}>
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="flex-start"
          sx={{ mb: 1.25 }}
        >
          <Stack
            direction="row"
            spacing={0.75}
            alignItems="center"
            flexWrap="wrap"
            useFlexGap
          >
            <Typography
              variant="caption"
              fontWeight={700}
              color="text.secondary"
            >
              #{idx + 1}
            </Typography>
            {ex.category && (
              <Chip
                size="small"
                label={categoryLabel(ex.category)}
                color={categoryColor(ex.category)}
                sx={{ height: 18, fontSize: "0.65rem" }}
              />
            )}
            {ex.core && (
              <Chip
                size="small"
                label="Core"
                color="success"
                variant="outlined"
                sx={{ height: 18, fontSize: "0.65rem" }}
              />
            )}
            {ex.description && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ fontStyle: "italic" }}
              >
                {ex.description}
              </Typography>
            )}
          </Stack>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            {!ex.deidentified && ex.input && (
              <Chip
                size="small"
                label="Check for patient data"
                color="warning"
                sx={{ height: 18, fontSize: "0.62rem" }}
              />
            )}
            <Tooltip title={editing ? "Show preview" : "Edit this example"}>
              <IconButton size="small" onClick={() => setEditing((v) => !v)}>
                {editing ? (
                  <VisibilityIcon fontSize="small" />
                ) : (
                  <EditIcon fontSize="small" />
                )}
              </IconButton>
            </Tooltip>
            <IconButton size="small" onClick={() => onRemove(ex.id)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Stack>

        {editing ? (
          <ExampleEditMode ex={ex} onChange={onChange} />
        ) : (
          <ExamplePreviewMode ex={ex} />
        )}
      </CardContent>
    </Card>
  );
}

function ExampleEditMode({
  ex,
  onChange,
}: {
  ex: FewShotExample;
  onChange: ExampleCardProps["onChange"];
}) {
  return (
    <Stack spacing={1.25}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField
          size="small"
          label="What does this example show?"
          placeholder="e.g. Simple negation of a finding"
          value={ex.description}
          sx={{ flex: 2 }}
          onChange={(e) => onChange(ex.id, "description", e.target.value)}
        />
        <FormControl size="small" sx={{ flex: 1, minWidth: 170 }}>
          <InputLabel>Category</InputLabel>
          <Select
            label="Category"
            value={ex.category}
            onChange={(e) => onChange(ex.id, "category", e.target.value)}
          >
            {CATEGORY_OPTIONS.filter((o) => o.value).map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ flex: 1, minWidth: 150 }}>
          <InputLabel>Provider</InputLabel>
          <Select
            label="Provider"
            value={ex.model_scope || "any"}
            onChange={(e) => onChange(ex.id, "model_scope", e.target.value)}
          >
            {SCOPE_OPTIONS.map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>

      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={Boolean(ex.core)}
            onChange={(e) => onChange(ex.id, "core", e.target.checked)}
            color="success"
          />
        }
        label={<Typography variant="caption">Core (always included)</Typography>}
        sx={{ m: 0 }}
      />

      <TextField
        fullWidth
        size="small"
        label="Clinical text the AI sees"
        placeholder="[s0] No fever."
        multiline
        minRows={1}
        value={ex.input}
        onChange={(e) => onChange(ex.id, "input", e.target.value)}
        helperText="Start each sentence with [s0], [s1], etc."
      />

      <TextField
        fullWidth
        size="small"
        label="Expected output JSON"
        placeholder='{"terms": [...]}'
        multiline
        minRows={3}
        value={ex.output}
        onChange={(e) => onChange(ex.id, "output", e.target.value)}
        inputProps={{
          style: { fontFamily: "monospace", fontSize: "0.78rem" },
        }}
      />

      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={ex.deidentified}
            onChange={(e) => onChange(ex.id, "deidentified", e.target.checked)}
            color="success"
          />
        }
        label={
          <Typography
            variant="caption"
            color={ex.deidentified ? "success.main" : "text.secondary"}
          >
            {ex.deidentified
              ? "Confirmed: no patient-identifiable data"
              : "Mark as de-identified when you've checked for names/numbers"}
          </Typography>
        }
        sx={{ m: 0 }}
      />
    </Stack>
  );
}

function ExamplePreviewMode({ ex }: { ex: FewShotExample }) {
  return (
    <Stack spacing={1.25}>
      <Box>
        <Typography
          variant="caption"
          color="text.disabled"
          fontWeight={600}
          sx={{ display: "block", mb: 0.5 }}
        >
          CLINICAL TEXT
        </Typography>
        <InputDisplay text={ex.input} />
      </Box>
      <Divider />
      <Box>
        <Typography
          variant="caption"
          color="text.disabled"
          fontWeight={600}
          sx={{ display: "block", mb: 0.5 }}
        >
          EXPECTED OUTPUT
        </Typography>
        <OutputPreview outputJson={ex.output} />
      </Box>
    </Stack>
  );
}
