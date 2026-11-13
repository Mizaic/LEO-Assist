/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Radio from "@mui/material/Radio";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import { friendlyTerm } from "./copy";
import type { LogicSeed } from "./types";

export interface SeedRowProps {
  seed: LogicSeed;
  isPrimary: boolean;
  canRemove: boolean;
  /** True when this X undoes the whole wizard match, not just one synonym. */
  removeClearsMatch?: boolean;
  onPickPrimary: () => void;
  onToggleDescendants: () => void;
  onSetDistance: (d: number | null) => void;
  onRemove: () => void;
}

export default function SeedRow({
  seed,
  isPrimary,
  canRemove,
  removeClearsMatch = false,
  onPickPrimary,
  onToggleDescendants,
  onSetDistance,
  onRemove,
}: SeedRowProps) {
  const includeDescendants = seed.include_descendants ?? true;
  const friendly = friendlyTerm(seed.preferred_term);

  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="center"
      sx={{
        px: 0.75,
        py: 0.5,
        borderRadius: 1,
        bgcolor: isPrimary ? "primary.50" : "background.paper",
        border: "1px solid",
        borderColor: isPrimary ? "primary.100" : "transparent",
        transition: "background-color 120ms ease, border-color 120ms ease",
      }}
    >
      <Tooltip title="Use as the chip label" arrow>
        <Radio
          size="small"
          checked={isPrimary}
          onChange={onPickPrimary}
          inputProps={{ "aria-label": `Use ${friendly} as the chip label` }}
          sx={{ p: 0.25 }}
        />
      </Tooltip>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <Typography
            variant="body2"
            sx={{
              fontWeight: isPrimary ? 700 : 500,
              lineHeight: 1.25,
              color: isPrimary ? "primary.dark" : "text.primary",
            }}
            noWrap
          >
            {friendly}
          </Typography>
          {isPrimary && (
            <Box
              component="span"
              sx={{
                fontSize: "0.6rem",
                fontWeight: 700,
                letterSpacing: 0.5,
                px: 0.5,
                py: "1px",
                borderRadius: 0.5,
                color: "primary.contrastText",
                bgcolor: "primary.main",
                textTransform: "uppercase",
              }}
              aria-hidden
            >
              Label
            </Box>
          )}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          code {seed.snomed_concept_id}
          {seed.semantic_tag ? ` -- ${seed.semantic_tag}` : ""}
        </Typography>
      </Box>
      <Tooltip
        title={
          includeDescendants
            ? "Also matches more specific codes (descendants). Click to switch off."
            : "Only matches this exact code. Click to also include more specific codes."
        }
        arrow
      >
        <Switch
          size="small"
          checked={includeDescendants}
          onChange={onToggleDescendants}
          slotProps={{
            input: {
              role: "switch",
              "aria-label": `Include descendants for ${friendly}`,
            },
          }}
        />
      </Tooltip>
      {includeDescendants && (
        <Tooltip title="How many levels of more specific codes to include. Minimum is 1." arrow>
          <TextField
            size="small"
            type="number"
            value={seed.distance_child ?? ""}
            placeholder="depth"
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") {
                onSetDistance(null);
                return;
              }
              const n = Number(raw);
              if (!Number.isFinite(n)) {
                onSetDistance(null);
                return;
              }
              onSetDistance(Math.max(1, Math.floor(n)));
            }}
            inputProps={{
              min: 1,
              max: 12,
              "aria-label": `Descendant depth for ${friendly}, minimum 1`,
            }}
            sx={{ width: 64 }}
          />
        </Tooltip>
      )}
      <Tooltip
        title={
          !canRemove
            ? "A chip needs at least one code."
            : removeClearsMatch
              ? "Remove this match so you can pick a different code."
              : "Remove this code"
        }
        arrow
      >
        <span>
          <IconButton
            size="small"
            disabled={!canRemove}
            onClick={onRemove}
            aria-label={
              removeClearsMatch
                ? `Remove match for ${friendly}`
                : `Remove ${friendly} from this chip`
            }
          >
            <CloseIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </span>
      </Tooltip>
    </Stack>
  );
}
