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
 * Inline expandable list of SNOMED descendants for a single seed.
 *
 * Reviewers need to be able to *see* what an "include descendants,
 * depth N" toggle will actually match in the bitmap. Without this
 * affordance the depth control is opaque and the rule cannot be
 * audited for unintended children -- a clinical safety gap in the
 * synonym set workflow (R-LEO-AI-509).
 *
 * Behaviour
 *  - Collapsed by default. Header shows "Show codes" / "Hide codes".
 *  - On expand, fetches /api/terminology/concepts/{id}/descendants
 *    at the seed's current depth (or the rule-level default).
 *  - Re-fetches whenever the seed's depth changes so the preview
 *    always reflects the saved configuration.
 *  - Each row shows the term, its SNOMED id, and a Block button so
 *    the reviewer can immediately exclude an unintended descendant
 *    without leaving the popover.
 *  - Already-blocked descendants render with a strike-through and a
 *    BLOCKED chip so the reviewer can see them in the same list.
 *  - When ``include_descendants`` is false, no fetch happens; the
 *    panel renders the simple "Only this exact code" message.
 *
 * Backed by the existing terminology endpoint:
 *   GET /api/terminology/concepts/{concept_id}/descendants
 *     ?depth={1..5}&limit={1..500}
 *
 * Design Controls: UN-LEO-AI-093, DI-LEO-AI-511, R-LEO-AI-509,
 *                  VT-LEO-AI-510.
 */

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import BlockIcon from "@mui/icons-material/Block";
import CloseIcon from "@mui/icons-material/Close";
import ExpandLessRoundedIcon from "@mui/icons-material/ExpandLessRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";

import { friendlyTerm } from "./copy";

/**
 * The terminology API returns rows shaped like:
 *   { snomed_concept_id, term, semantic_tag, surface_form_count?, surface_forms? }
 * (see DESCENDANTS_TEMPLATE in services/api/app/models/neo4j_schema.py
 *  -- d.fsn AS term).
 *
 * We accept ``preferred_term`` too so other callers / mocks that use the
 * search-endpoint shape keep working.
 */
interface DescendantRow {
  snomed_concept_id: string;
  term?: string;
  preferred_term?: string;
  semantic_tag?: string;
}

function rowTerm(r: DescendantRow): string {
  return r.preferred_term || r.term || "";
}

interface Props {
  seedConceptId: string;
  seedTerm: string;
  /** True when the seed's include_descendants toggle is on. */
  includeDescendants: boolean;
  /** Effective depth for this seed (per-seed override or rule default). */
  depth: number;
  /** SNOMED ids that are already in the chip's exclusion list. */
  excludedIds: string[];
  /** Add a SNOMED id to the chip's exclusion list. */
  onBlock: (conceptId: string) => void;
  /** Remove a SNOMED id from the chip's exclusion list. */
  onUnblock: (conceptId: string) => void;
}

const HARD_PREVIEW_LIMIT = 200;
const DEFAULT_DEPTH_FALLBACK = 3;

export default function SeedDescendantsList({
  seedConceptId,
  seedTerm,
  includeDescendants,
  depth,
  excludedIds,
  onBlock,
  onUnblock,
}: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<DescendantRow[] | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  /**
   * The depth prop is always a positive integer by the time it reaches this
   * component (the caller clamps to >=1 -- see SynonymChipEditor.tsx). We
   * only fall back to the rule default for a genuinely missing value, so a
   * real depth change always produces a different API call. Previously any
   * value <=0 was silently rewritten to 3, which made distinct depths the
   * author picked (e.g. 0 vs 1) look identical in the preview.
   */
  const effectiveDepth = useMemo(() => {
    if (typeof depth === "number" && Number.isFinite(depth) && depth >= 1) {
      return depth;
    }
    return DEFAULT_DEPTH_FALLBACK;
  }, [depth]);

  useEffect(() => {
    if (!open || !includeDescendants) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `/api/terminology/concepts/${encodeURIComponent(seedConceptId)}/descendants?depth=${Math.min(
            5,
            Math.max(1, effectiveDepth),
          )}&limit=${HARD_PREVIEW_LIMIT}`,
        );
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const body = (await res.json()) as DescendantRow[];
        if (!cancelled) {
          setRows(Array.isArray(body) ? body : []);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load codes");
          setRows([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [open, includeDescendants, seedConceptId, effectiveDepth, reloadKey]);

  const blockedSet = useMemo(() => new Set(excludedIds), [excludedIds]);

  if (!includeDescendants) {
    return (
      <Box
        sx={{
          mt: 0.75,
          px: 1,
          py: 0.75,
          borderRadius: 1,
          border: "1px dashed",
          borderColor: "divider",
          bgcolor: "background.paper",
        }}
      >
        <Typography variant="caption" color="text.secondary">
          Only the exact code <strong>{seedConceptId}</strong> will fire.
          Turn on the toggle to also include more specific codes.
        </Typography>
      </Box>
    );
  }

  const rowsCount = rows?.length ?? 0;
  const showCodesLabel = open
    ? `Hide codes`
    : `Show codes (up to ${HARD_PREVIEW_LIMIT})`;

  return (
    <Box sx={{ mt: 0.75 }}>
      <Stack direction="row" alignItems="center" spacing={0.5}>
        <Button
          size="small"
          onClick={() => setOpen((v) => !v)}
          startIcon={
            open ? (
              <ExpandLessRoundedIcon fontSize="small" />
            ) : (
              <ExpandMoreRoundedIcon fontSize="small" />
            )
          }
          aria-expanded={open}
          aria-label={
            open
              ? `Hide the codes covered by ${friendlyTerm(seedTerm)}`
              : `Show the codes covered by ${friendlyTerm(seedTerm)} at depth ${effectiveDepth}`
          }
          sx={{
            textTransform: "none",
            fontWeight: 600,
            color: "primary.dark",
            justifyContent: "flex-start",
            px: 0.75,
            py: 0.25,
            minHeight: 0,
          }}
        >
          {showCodesLabel}
        </Button>
        {open && rows && (
          <Typography variant="caption" color="text.secondary">
            {rowsCount === HARD_PREVIEW_LIMIT
              ? `${HARD_PREVIEW_LIMIT}+ codes (showing first ${HARD_PREVIEW_LIMIT})`
              : `${rowsCount} code${rowsCount === 1 ? "" : "s"}`}
          </Typography>
        )}
        {open && (
          <Tooltip title="Reload the codes" arrow>
            <span>
              <IconButton
                size="small"
                onClick={() => setReloadKey((k) => k + 1)}
                disabled={loading}
                aria-label="Reload the codes for this seed"
                sx={{ p: 0.25 }}
              >
                <RefreshRoundedIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        )}
      </Stack>
      <Collapse in={open} unmountOnExit timeout={180}>
        <Box
          sx={{
            mt: 0.5,
            borderRadius: 1,
            border: "1px solid",
            borderColor: "divider",
            bgcolor: "background.paper",
            maxHeight: 220,
            overflowY: "auto",
          }}
          role="list"
          aria-label={`Codes covered by ${friendlyTerm(seedTerm)} at depth ${effectiveDepth}`}
        >
          {loading && (
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{ p: 1.5 }}
            >
              <CircularProgress size={14} />
              <Typography variant="caption" color="text.secondary">
                Loading codes...
              </Typography>
            </Stack>
          )}
          {!loading && error && (
            <Alert severity="warning" sx={{ m: 1, py: 0.5 }} role="status">
              Could not load the codes ({error}). Try again.
            </Alert>
          )}
          {!loading && !error && rows && rows.length === 0 && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", p: 1.5 }}
            >
              No more specific codes were found at this depth.
            </Typography>
          )}
          {!loading && !error && rows && rows.length > 0 && (
            <Stack divider={<Box sx={{ borderTop: "1px solid", borderColor: "divider" }} />}>
              {rows.map((r) => {
                const isBlocked = blockedSet.has(r.snomed_concept_id);
                return (
                  <DescendantRowView
                    key={r.snomed_concept_id}
                    row={r}
                    isBlocked={isBlocked}
                    onBlock={onBlock}
                    onUnblock={onUnblock}
                  />
                );
              })}
            </Stack>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}

function DescendantRowView({
  row,
  isBlocked,
  onBlock,
  onUnblock,
}: {
  row: DescendantRow;
  isBlocked: boolean;
  onBlock: (conceptId: string) => void;
  onUnblock: (conceptId: string) => void;
}) {
  const friendly = friendlyTerm(rowTerm(row)) || `code ${row.snomed_concept_id}`;
  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      sx={{
        px: 1,
        py: 0.5,
        bgcolor: isBlocked ? "error.50" : "transparent",
      }}
      role="listitem"
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          variant="body2"
          sx={{
            fontWeight: 500,
            lineHeight: 1.2,
            color: isBlocked ? "text.disabled" : "text.primary",
            textDecoration: isBlocked ? "line-through" : "none",
          }}
          noWrap
          title={friendly}
        >
          {friendly}
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block" }}
        >
          code {row.snomed_concept_id}
          {row.semantic_tag ? ` -- ${row.semantic_tag}` : ""}
        </Typography>
      </Box>
      {isBlocked ? (
        <Stack direction="row" spacing={0.25} alignItems="center">
          <Box
            component="span"
            aria-hidden
            sx={{
              height: 22,
              px: 0.75,
              display: "inline-flex",
              alignItems: "center",
              fontSize: "0.65rem",
              fontWeight: 700,
              borderRadius: 999,
              border: "1px solid",
              borderColor: "error.light",
              color: "error.dark",
              bgcolor: "error.50",
            }}
          >
            Blocked
          </Box>
          <Tooltip title={`Unblock ${friendly}`} arrow>
            <IconButton
              size="small"
              onClick={() => onUnblock(row.snomed_concept_id)}
              aria-label={`Unblock ${friendly}`}
              sx={{ p: 0.25, color: "error.dark" }}
            >
              <CloseIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        </Stack>
      ) : (
        <Tooltip title={`Block ${friendly} from firing this rule`} arrow>
          <Button
            size="small"
            onClick={() => onBlock(row.snomed_concept_id)}
            startIcon={<BlockIcon sx={{ fontSize: 14 }} />}
            aria-label={`Block ${friendly} from firing this rule`}
            sx={{
              textTransform: "none",
              fontWeight: 600,
              color: "error.dark",
              minHeight: 0,
              py: 0.25,
              px: 0.75,
            }}
          >
            Block
          </Button>
        </Tooltip>
      )}
    </Stack>
  );
}
