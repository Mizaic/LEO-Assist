/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

/** One Validation Lab test-patient card. Atlas: DI-EB716E68 / DI-12D40786 */

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";

import { caseSummary, caseTags } from "./caseCardMeta";
import type { LabCase } from "./labApi";

function scenarioLabel(value?: string): string {
  if (value === "spo_ag") return "SPoA A&G";
  if (value === "ras_referral") return "RAS referral";
  return "Generic";
}

interface Props {
  caseItem: LabCase;
  selected: boolean;
  checked: boolean;
  renaming: boolean;
  testing: boolean;
  busy: boolean;
  editTitle: string;
  onEditTitle: (value: string) => void;
  onToggleCheck: () => void;
  onSelect: () => void;
  onStartRename: () => void;
  onCancelRename: () => void;
  onSaveRename: () => void;
  onViewPatient: () => void;
  onTest: () => void;
  onDelete: () => void;
  onTagClick: (tag: string) => void;
}

export default function TestPatientCard({
  caseItem: c,
  selected,
  checked,
  renaming,
  testing,
  busy,
  editTitle,
  onEditTitle,
  onToggleCheck,
  onSelect,
  onStartRename,
  onCancelRename,
  onSaveRename,
  onViewPatient,
  onTest,
  onDelete,
  onTagClick,
}: Props) {
  const summary = caseSummary(c);
  const tags = caseTags(c);
  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: selected ? "primary.main" : "divider",
        bgcolor: selected ? "primary.50" : "background.paper",
        borderRadius: 1,
        p: 1,
      }}
    >
      {renaming ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            size="small"
            fullWidth
            value={editTitle}
            onChange={(e) => onEditTitle(e.target.value)}
            inputProps={{ "data-testid": "validation-lab-rename-input" }}
          />
          <Button
            size="small"
            variant="contained"
            disabled={busy || !editTitle.trim()}
            onClick={onSaveRename}
            data-testid="validation-lab-rename-save"
          >
            Save
          </Button>
          <Button size="small" onClick={onCancelRename}>
            Cancel
          </Button>
        </Stack>
      ) : (
        <Stack spacing={0.5}>
          <Stack direction="row" spacing={1} alignItems="flex-start">
            <Checkbox
              size="small"
              checked={checked}
              disabled={busy}
              onChange={onToggleCheck}
              inputProps={{
                "aria-label": `Select ${c.title || c.id}`,
              }}
              data-testid={`validation-lab-check-${c.id}`}
            />
            <Button
              variant="text"
              onClick={onSelect}
              sx={{
                flex: 1,
                justifyContent: "flex-start",
                textAlign: "left",
                textTransform: "none",
                color: "text.primary",
              }}
              data-testid={`validation-lab-case-${c.id}`}
            >
              <Box sx={{ textAlign: "left" }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {c.title || c.id}
                </Typography>
                {summary ? (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block" }}
                    data-testid={`validation-lab-summary-${c.id}`}
                  >
                    {summary}
                  </Typography>
                ) : null}
                <Typography variant="caption" color="text.secondary">
                  {scenarioLabel(c.scenario_type)} · {c.case_type || "referral"}
                  {c.has_gold ? " · gold" : ""}
                </Typography>
              </Box>
            </Button>
            <Stack direction="row" spacing={0.5} alignItems="center">
              {c.has_gold ? (
                <Chip size="small" color="success" label="gold" />
              ) : null}
              {testing ? (
                <Chip
                  size="small"
                  color="info"
                  label="testing"
                  data-testid={`validation-lab-testing-${c.id}`}
                />
              ) : null}
              <IconButton
                size="small"
                aria-label={`Test pipeline for ${c.title || c.id}`}
                disabled={busy || testing}
                onClick={onTest}
                data-testid={`validation-lab-test-${c.id}`}
              >
                <PlayArrowOutlinedIcon fontSize="small" />
              </IconButton>
              <IconButton
                size="small"
                aria-label={`View patient ${c.title || c.id}`}
                disabled={busy || !c.patient_id}
                onClick={onViewPatient}
                data-testid={`validation-lab-view-${c.id}`}
              >
                <VisibilityOutlinedIcon fontSize="small" />
              </IconButton>
              <IconButton
                size="small"
                aria-label={`Rename ${c.title || c.id}`}
                disabled={busy}
                onClick={onStartRename}
                data-testid={`validation-lab-rename-${c.id}`}
              >
                <EditOutlinedIcon fontSize="small" />
              </IconButton>
              <IconButton
                size="small"
                aria-label={`Delete ${c.title || c.id}`}
                disabled={busy}
                onClick={onDelete}
                data-testid={`validation-lab-delete-${c.id}`}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Stack>
          {tags.length > 0 ? (
            <Stack
              direction="row"
              spacing={0.5}
              useFlexGap
              flexWrap="wrap"
              data-testid={`validation-lab-tags-${c.id}`}
            >
              {tags.map((tag) => (
                <Chip
                  key={`${c.id}-${tag}`}
                  size="small"
                  label={tag}
                  onClick={() => onTagClick(tag)}
                />
              ))}
            </Stack>
          ) : null}
        </Stack>
      )}
    </Box>
  );
}
