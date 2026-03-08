"use client";

/**
 * GuidelineSubgraphDrawer
 *
 * Shows exactly what is stored in Neo4j for a given NICE guideline:
 * chapters, recommendations with their full verbatim text, and any rules.
 * Designed so admins can verify the graph content without opening Neo4j Browser.
 *
 * Data source: GET /api/nice/{code}/subgraph
 */

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import GavelIcon from "@mui/icons-material/Gavel";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import TextSnippetIcon from "@mui/icons-material/TextSnippet";

// ── Types ─────────────────────────────────────────────────────────────────────

interface RuleEntry {
  rule_id: string;
  status: string;
  name: string;
  created_at: string;
}

interface RecEntry {
  rec_id: string;
  rec_title: string;
  verbatim: string;
  urgency: string;
  strength: string;
  /** Cancer site / topic label from the NICE section heading, e.g. "Lung cancer" */
  section_title: string;
  /** True = canonical numbered recommendation eligible for rule generation.
   *  False = cross-reference table entry (symptom/sign index) — NOT used for rules. */
  is_normative: boolean;
  version_id: string;
  rules: RuleEntry[];
}

interface ChapterEntry {
  chapter_id: string;
  chapter_title: string;
  order: number;
  recommendations: RecEntry[];
}

interface SubgraphData {
  guideline_id: string;
  guideline_title: string;
  ingest_version: number | null;
  publication_date: string;
  chapters: ChapterEntry[];
  totals: {
    chapters: number;
    recommendations: number;
    rules: number;
  };
}

interface Props {
  code: string | null;
  onClose: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const URGENCY_LABEL: Record<string, string> = {
  urgent_2w: "2WW",
  immediate: "Immediate",
  very_urgent_48h: "48 h",
  urgent_1w: "1 wk",
  routine: "Routine",
};

const RULE_STATUS_COLOR: Record<string, "success" | "warning" | "error" | "default"> = {
  active: "success",
  pending_review: "warning",
  rejected: "error",
  superseded: "default",
};

function RuleChip({ rule }: { rule: RuleEntry }) {
  const color = RULE_STATUS_COLOR[rule.status] ?? "default";
  const icon =
    rule.status === "active" ? (
      <CheckCircleIcon sx={{ fontSize: 13 }} />
    ) : rule.status === "pending_review" ? (
      <HourglassEmptyIcon sx={{ fontSize: 13 }} />
    ) : (
      <GavelIcon sx={{ fontSize: 13 }} />
    );
  return (
    <Tooltip title={rule.name || rule.rule_id} arrow>
      <Chip
        icon={icon}
        label={rule.status.replace("_", " ")}
        size="small"
        color={color}
        variant="outlined"
        sx={{ height: 20, fontSize: "0.68rem", mr: 0.5, mb: 0.5 }}
      />
    </Tooltip>
  );
}

function RecommendationRow({ rec }: { rec: RecEntry }) {
  const [open, setOpen] = useState(false);
  const hasText = rec.verbatim && rec.verbatim.trim().length > 0;
  const preview = rec.verbatim ? rec.verbatim.slice(0, 120) : "(no text stored)";
  const borderColor = rec.is_normative ? "grey.200" : "warning.light";

  return (
    <Box sx={{ borderLeft: "2px solid", borderColor, pl: 1.5, mb: 0.5 }}>
      <Stack
        direction="row"
        alignItems="flex-start"
        spacing={0.5}
        sx={{ cursor: hasText ? "pointer" : "default" }}
        onClick={() => hasText && setOpen((o) => !o)}
      >
        {hasText ? (
          open ? (
            <ExpandMoreIcon sx={{ fontSize: 16, mt: 0.3, color: "text.secondary", flexShrink: 0 }} />
          ) : (
            <ChevronRightIcon sx={{ fontSize: 16, mt: 0.3, color: "text.secondary", flexShrink: 0 }} />
          )
        ) : (
          <Box sx={{ width: 16, flexShrink: 0 }} />
        )}

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
            {rec.rec_title && (
              <Typography
                variant="caption"
                sx={{ fontWeight: 700, color: "primary.main", fontFamily: "monospace" }}
              >
                {rec.rec_title}
              </Typography>
            )}
            {!rec.is_normative && (
              <Tooltip title="Cross-reference table entry — not used for rule generation" arrow>
                <Chip
                  label="cross-ref"
                  size="small"
                  color="warning"
                  variant="filled"
                  sx={{ height: 16, fontSize: "0.60rem" }}
                />
              </Tooltip>
            )}
            {rec.urgency && URGENCY_LABEL[rec.urgency] && (
              <Chip
                label={URGENCY_LABEL[rec.urgency]}
                size="small"
                color="warning"
                variant="outlined"
                sx={{ height: 16, fontSize: "0.62rem" }}
              />
            )}
            {rec.strength && rec.strength !== "unspecified" && (
              <Chip
                label={rec.strength}
                size="small"
                variant="outlined"
                sx={{ height: 16, fontSize: "0.62rem" }}
              />
            )}
          </Stack>

          {/* Preview text */}
          <Typography
            variant="body2"
            sx={{
              fontSize: "0.78rem",
              color: hasText ? "text.primary" : "text.disabled",
              fontStyle: hasText ? "normal" : "italic",
              mt: 0.2,
            }}
          >
            {preview}
            {rec.verbatim && rec.verbatim.length > 120 && !open ? "…" : ""}
          </Typography>

          {/* Rules */}
          {rec.rules.length > 0 && (
            <Box sx={{ mt: 0.4 }}>
              {rec.rules.map((r) => (
                <RuleChip key={r.rule_id} rule={r} />
              ))}
            </Box>
          )}
        </Box>
      </Stack>

      {/* Full text */}
      <Collapse in={open}>
        <Box
          sx={{
            mt: 0.5,
            ml: 2,
            p: 1.2,
            bgcolor: "grey.50",
            borderRadius: 1,
            border: "1px solid",
            borderColor: "grey.200",
          }}
        >
          <Typography variant="body2" sx={{ fontSize: "0.82rem", lineHeight: 1.6 }}>
            {rec.verbatim}
          </Typography>
          <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5, display: "block" }}>
            ID: {rec.rec_id}
          </Typography>
        </Box>
      </Collapse>
    </Box>
  );
}

/**
 * Groups an array of recommendations by their section_title (cancer site / topic).
 * Returns an ordered list of [sectionLabel, recs[]] pairs.
 * Recs with no section_title are grouped under an empty-string key and shown first.
 */
function groupBySectionTitle(recs: RecEntry[]): [string, RecEntry[]][] {
  const map = new Map<string, RecEntry[]>();
  for (const rec of recs) {
    const key = rec.section_title || "";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(rec);
  }
  // Put un-labelled recs first, then alphabetical by label
  return [...map.entries()].sort(([a], [b]) => {
    if (!a) return -1;
    if (!b) return 1;
    return a.localeCompare(b);
  });
}

function ChapterAccordion({ chapter }: { chapter: ChapterEntry }) {
  const [open, setOpen] = useState(false);
  const ruleCount = chapter.recommendations.reduce((n, r) => n + r.rules.length, 0);
  const normativeCount = chapter.recommendations.filter((r) => r.is_normative).length;
  const crossRefCount = chapter.recommendations.length - normativeCount;
  const groups = groupBySectionTitle(chapter.recommendations.filter((r) => r.is_normative));
  // More than one distinct non-empty section title → worth grouping
  const hasGroups = groups.length > 1 || (groups.length === 1 && groups[0][0] !== "");

  return (
    <Box sx={{ mb: 1 }}>
      <Stack
        direction="row"
        alignItems="center"
        spacing={0.5}
        sx={{
          cursor: "pointer",
          p: 0.8,
          borderRadius: 1,
          bgcolor: open ? "primary.50" : "grey.100",
          "&:hover": { bgcolor: open ? "primary.100" : "grey.200" },
        }}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? (
          <ExpandMoreIcon fontSize="small" color="primary" />
        ) : (
          <ChevronRightIcon fontSize="small" />
        )}
        <MenuBookIcon sx={{ fontSize: 15, color: "text.secondary" }} />
        <Typography variant="body2" sx={{ fontWeight: 600, flex: 1, fontSize: "0.82rem" }}>
          {chapter.chapter_title || chapter.chapter_id}
        </Typography>
        <Chip
          label={`${normativeCount} rec`}
          size="small"
          color={normativeCount > 0 ? "primary" : "default"}
          variant="outlined"
          sx={{ height: 18, fontSize: "0.65rem" }}
        />
        {crossRefCount > 0 && (
          <Tooltip title="Cross-reference entries — not used for rule generation" arrow>
            <Chip
              label={`${crossRefCount} cross-ref`}
              size="small"
              color="warning"
              variant="outlined"
              sx={{ height: 18, fontSize: "0.65rem" }}
            />
          </Tooltip>
        )}
        {ruleCount > 0 && (
          <Chip
            label={`${ruleCount} rule${ruleCount !== 1 ? "s" : ""}`}
            size="small"
            color="success"
            variant="outlined"
            sx={{ height: 18, fontSize: "0.65rem" }}
          />
        )}
      </Stack>

      <Collapse in={open}>
        <Box sx={{ mt: 0.5, pl: 0.5 }}>
          {chapter.recommendations.length === 0 ? (
            <Typography variant="body2" color="text.disabled" sx={{ pl: 2, py: 0.5, fontSize: "0.78rem" }}>
              No recommendations stored in Neo4j for this chapter.
            </Typography>
          ) : hasGroups ? (
            /* ── Grouped by cancer site / section (normative only) ── */
            groups.map(([sectionLabel, recs]) => (
              <Box key={sectionLabel || "__ungrouped__"} sx={{ mb: 1 }}>
                <Stack
                  direction="row"
                  alignItems="center"
                  spacing={0.6}
                  sx={{
                    px: 1,
                    py: 0.4,
                    mb: 0.5,
                    bgcolor: "primary.50",
                    borderRadius: 0.8,
                    borderLeft: "3px solid",
                    borderColor: "primary.light",
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{ fontWeight: 700, color: "primary.dark", fontSize: "0.75rem" }}
                  >
                    {sectionLabel || "General"}
                  </Typography>
                  <Chip
                    label={`${recs.length}`}
                    size="small"
                    variant="outlined"
                    sx={{ height: 15, fontSize: "0.60rem", ml: "auto !important" }}
                  />
                </Stack>
                {recs.map((rec) => (
                  <RecommendationRow key={rec.rec_id} rec={rec} />
                ))}
              </Box>
            ))
          ) : (
            /* ── Flat list (normative, no section grouping) ── */
            chapter.recommendations
              .filter((r) => r.is_normative)
              .map((rec) => <RecommendationRow key={rec.rec_id} rec={rec} />)
          )}

          {/* ── Cross-reference entries (not used for rules) ── */}
          {crossRefCount > 0 && (
            <Box sx={{ mt: 1 }}>
              <Divider sx={{ mb: 0.8 }}>
                <Typography variant="caption" color="warning.main" sx={{ fontSize: "0.68rem" }}>
                  {crossRefCount} cross-reference {crossRefCount === 1 ? "entry" : "entries"} — not used for rule generation
                </Typography>
              </Divider>
              {chapter.recommendations
                .filter((r) => !r.is_normative)
                .map((rec) => <RecommendationRow key={rec.rec_id} rec={rec} />)}
            </Box>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function GuidelineSubgraphDrawer({ code, onClose }: Props) {
  const [data, setData] = useState<SubgraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (c: string) => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const r = await fetch(`/api/nice/${encodeURIComponent(c)}/subgraph`);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      setData(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load subgraph.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (code) load(code);
  }, [code, load]);

  const open = Boolean(code);
  const chaptersWithRecs = data?.chapters.filter((c) => c.recommendations.length > 0) ?? [];
  const chaptersEmpty = data?.chapters.filter((c) => c.recommendations.length === 0) ?? [];

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100vw", sm: 640 }, p: 0 } }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 2.5,
          py: 1.5,
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
          position: "sticky",
          top: 0,
          zIndex: 1,
        }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <AccountTreeIcon color="primary" fontSize="small" />
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
              {data?.guideline_title || code}
            </Typography>
            {data && (
              <Stack direction="row" spacing={1} sx={{ mt: 0.3 }} flexWrap="wrap">
                <Chip
                  label={`v${data.ingest_version ?? "?"}`}
                  size="small"
                  color={data.ingest_version && data.ingest_version > 1 ? "warning" : "default"}
                  sx={{ height: 18, fontSize: "0.65rem" }}
                />
                <Chip
                  label={`${data.totals.chapters} chapters`}
                  size="small"
                  variant="outlined"
                  sx={{ height: 18, fontSize: "0.65rem" }}
                />
                <Chip
                  label={`${data.totals.recommendations} recommendations`}
                  size="small"
                  color={data.totals.recommendations > 0 ? "primary" : "error"}
                  variant="outlined"
                  sx={{ height: 18, fontSize: "0.65rem" }}
                />
                {data.totals.rules > 0 && (
                  <Chip
                    label={`${data.totals.rules} rules`}
                    size="small"
                    color="success"
                    variant="outlined"
                    sx={{ height: 18, fontSize: "0.65rem" }}
                  />
                )}
              </Stack>
            )}
          </Box>
          <IconButton onClick={onClose} size="small" aria-label="Close subgraph view">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
      </Box>

      {/* Body */}
      <Box sx={{ p: 2, overflowY: "auto", flex: 1 }}>
        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress aria-label="Loading guideline subgraph from Neo4j" />
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {data && !loading && (
          <>
            {/* Health check banner */}
            {data.totals.recommendations === 0 ? (
              <Alert severity="error" sx={{ mb: 2 }}>
                <strong>No recommendations in Neo4j.</strong> The ingest may have failed or used an
                older pipeline version. Re-ingest this guideline to populate recommendation text.
              </Alert>
            ) : data.chapters.length === 0 ? (
              <Alert severity="warning" sx={{ mb: 2 }}>
                Recommendations exist but no chapters were found. This may indicate an older ingest
                that did not preserve the chapter hierarchy. Re-ingest to fix.
              </Alert>
            ) : null}

            {/* Chapters with recommendations */}
            {chaptersWithRecs.map((ch) => (
              <ChapterAccordion key={ch.chapter_id} chapter={ch} />
            ))}

            {/* Empty chapters (no recommendations — appendices etc.) */}
            {chaptersEmpty.length > 0 && (
              <>
                <Divider sx={{ my: 1.5 }}>
                  <Typography variant="caption" color="text.disabled">
                    {chaptersEmpty.length} chapter{chaptersEmpty.length !== 1 ? "s" : ""} with no
                    recommendations (appendices / evidence reviews)
                  </Typography>
                </Divider>
                {chaptersEmpty.map((ch) => (
                  <Box
                    key={ch.chapter_id}
                    sx={{
                      px: 1.5,
                      py: 0.6,
                      mb: 0.4,
                      bgcolor: "grey.50",
                      borderRadius: 1,
                      display: "flex",
                      alignItems: "center",
                      gap: 0.8,
                    }}
                  >
                    <TextSnippetIcon sx={{ fontSize: 14, color: "text.disabled" }} />
                    <Typography variant="caption" color="text.secondary">
                      {ch.chapter_title || ch.chapter_id}
                    </Typography>
                  </Box>
                ))}
              </>
            )}

            {/* Node ID legend */}
            <Divider sx={{ mt: 2, mb: 1 }} />
            <Typography variant="caption" color="text.disabled">
              Node IDs use version-scoped format: {code}:v{data.ingest_version}:CH###:SEC###:R###
            </Typography>
          </>
        )}
      </Box>
    </Drawer>
  );
}
