/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Hover/focus tooltip on a Depth control that previews which more
 * specific clinical codes the current depth would include. Keeps the
 * picker compact (progressive disclosure) while closing the same
 * safety gap SeedDescendantsList covers in the synonym editor: the
 * reviewer must be able to see what depth N will match.
 */
import { useState, type ReactElement } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { MULTI_CONCEPT_PICKER, friendlyTerm } from "./copy";
import {
  DESCENDANTS_PREVIEW_LIMIT,
  descendantDisplayTerm,
  useConceptDescendants,
} from "./useConceptDescendants";

/** Tall enough to show ~10 rows; the rest scrolls inside the tooltip. */
const TOOLTIP_LIST_MAX_HEIGHT = 220;

interface Props {
  conceptId: string;
  term: string;
  depth: number;
  children: ReactElement;
}

export default function DepthInclusionTooltip({
  conceptId,
  term,
  depth,
  children,
}: Props) {
  const [open, setOpen] = useState(false);
  const wantsPreview = open && depth > 0;
  const { loading, error, rows } = useConceptDescendants(
    conceptId,
    depth,
    wantsPreview,
  );

  return (
    <Tooltip
      arrow
      placement="right"
      // Interactive so the reviewer can scroll the code list without
      // the tooltip closing the moment the pointer leaves the Depth field.
      disableInteractive={false}
      enterDelay={280}
      leaveDelay={200}
      open={open}
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
      describeChild
      title={
        <DepthTooltipBody
          term={term}
          depth={depth}
          loading={loading}
          error={error}
          rows={rows}
        />
      }
      slotProps={{
        tooltip: {
          sx: {
            maxWidth: 320,
            bgcolor: "grey.900",
            color: "grey.100",
            "& .MuiTooltip-arrow": { color: "grey.900" },
          },
        },
      }}
    >
      {children}
    </Tooltip>
  );
}

function DepthTooltipBody({
  term,
  depth,
  loading,
  error,
  rows,
}: {
  term: string;
  depth: number;
  loading: boolean;
  error: string | null;
  rows: ReturnType<typeof useConceptDescendants>["rows"];
}) {
  const friendly = friendlyTerm(term);

  if (depth <= 0) {
    return (
      <Typography variant="caption" component="div">
        {MULTI_CONCEPT_PICKER.depthPreviewExact(friendly)}
      </Typography>
    );
  }

  if (loading || rows === null) {
    return (
      <Stack direction="row" spacing={1} alignItems="center" sx={{ py: 0.25 }}>
        <CircularProgress size={12} sx={{ color: "common.white" }} />
        <Typography variant="caption" component="div">
          {MULTI_CONCEPT_PICKER.depthPreviewLoading}
        </Typography>
      </Stack>
    );
  }

  if (error) {
    return (
      <Typography variant="caption" component="div">
        {MULTI_CONCEPT_PICKER.depthPreviewError}
      </Typography>
    );
  }

  if (rows.length === 0) {
    return (
      <Typography variant="caption" component="div">
        {MULTI_CONCEPT_PICKER.depthPreviewEmpty(friendly, depth)}
      </Typography>
    );
  }

  const capped = rows.length >= DESCENDANTS_PREVIEW_LIMIT;

  return (
    <Box>
      <Typography
        variant="caption"
        component="div"
        sx={{ fontWeight: 700, mb: 0.5, color: "grey.100" }}
      >
        {MULTI_CONCEPT_PICKER.depthPreviewHeading(friendly, depth, rows.length, capped)}
      </Typography>
      <Box
        component="ul"
        sx={{
          m: 0,
          pl: 1.75,
          maxHeight: TOOLTIP_LIST_MAX_HEIGHT,
          overflowY: "auto",
          // Keep scrollbar usable on dark charcoal without fighting the theme.
          scrollbarWidth: "thin",
          "&::-webkit-scrollbar": { width: 6 },
          "&::-webkit-scrollbar-thumb": {
            bgcolor: "grey.600",
            borderRadius: 3,
          },
        }}
      >
        {rows.map((row) => (
          <Typography
            key={row.snomed_concept_id}
            component="li"
            variant="caption"
            sx={{ display: "list-item", color: "grey.100", py: 0.15 }}
          >
            {friendlyTerm(descendantDisplayTerm(row))}
          </Typography>
        ))}
      </Box>
      {capped && (
        <Typography
          variant="caption"
          component="div"
          sx={{ mt: 0.5, opacity: 0.85, color: "grey.300" }}
        >
          {MULTI_CONCEPT_PICKER.depthPreviewApiCap}
        </Typography>
      )}
    </Box>
  );
}
