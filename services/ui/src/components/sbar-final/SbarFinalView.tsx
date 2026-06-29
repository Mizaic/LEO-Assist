/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

/**
 * Reusable, standalone SBAR (final) renderer.
 *
 * The SBAR (Situation, Background, Assessment, Recommendation) Markdown
 * payload produced by the SBAR pipeline (DI-LEO-AI-191/194) is split on
 * its top-level ``## Situation`` / ``## Background`` / ``## Assessment``
 * / ``## Recommendation`` headings and each section is rendered as its
 * own themed card (NHS SBAR communication-training palette) with the
 * Tiptap-backed shared MarkdownEditor in view mode.
 *
 * Two surfaces are exported:
 *   - ``SbarFinalView``    inline / embeddable card stack
 *   - ``SbarFinalDialog``  same view inside an MUI Dialog
 *
 * Both take a Markdown string and a ``testOnly`` flag (defaulting to
 * ``true`` -- this view is for reviewers and demos, never an
 * authoritative clinical record). External applications can import this
 * module without depending on the playground or the SBAR pipeline
 * hooks.
 *
 * Risks addressed:
 *   - R-LEO-AI-185 (test-only labelling) is preserved by the chip
 *     in the dialog title and the optional banner in the inline view.
 */
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { useMemo, useState } from "react";
import {
  CompletenessPill,
  type CompletenessFinding,
} from "./CompletenessPill";
import MarkdownEditor from "@/components/markdown-editor/MarkdownEditor";

export type SbarStageName =
  | "situation"
  | "background"
  | "assessment"
  | "recommendation";

export const STAGE_LABELS: Record<SbarStageName, string> = {
  situation: "Situation",
  background: "Background",
  assessment: "Assessment",
  recommendation: "Recommendation",
};

// SBAR stage colour palette - aligned with the NHS visual standard for
// SBAR communication training so reviewers can scan the four sections
// at a glance. Exported so embedders can match chrome (e.g. tab
// indicators, side-rail accents) to the same palette.
export const STAGE_THEME: Record<
  SbarStageName,
  { accent: string; tint: string; ink: string }
> = {
  situation: { accent: "#2563eb", tint: "#eff6ff", ink: "#1e3a8a" },
  background: { accent: "#7c3aed", tint: "#f5f3ff", ink: "#5b21b6" },
  assessment: { accent: "#d97706", tint: "#fffbeb", ink: "#92400e" },
  recommendation: { accent: "#0d9488", tint: "#f0fdfa", ink: "#115e59" },
};

const SECTION_ORDER: SbarStageName[] = [
  "situation",
  "background",
  "assessment",
  "recommendation",
];

export interface SbarSection {
  stage: SbarStageName;
  body: string;
}

/**
 * Structured per-partition summary for the SBAR Background stage.
 * Mirrors the wire shape returned by libs/sbar/prompt_calls.py
 * ``_build_part_summary`` and persisted as ``background_parts`` on
 * the :Assessment node. Passing this as a typed prop is the
 * canonical way to populate the "Show source records" disclosure;
 * callers should NOT try to parse source ids out of the markdown.
 */
export interface SbarBackgroundPart {
  index: number;
  total: number;
  recordCount: number;
  recordRange: [number, number];
  sourceIds: string[];
  status: "completed" | "failed";
  errorCode?: string | null;
  errorMessage?: string | null;
}

// Belt-and-braces strip for legacy ``<!-- sources: ... -->`` HTML
// comments. The pipeline stopped emitting these in favour of the
// structured ``backgroundParts`` prop, but :Assessment rows persisted
// before that change still have them inline in ``a.background``. The
// Tiptap markdown view runs with ``html: false`` so without this
// cleanup the raw UUIDs would show up as visible text.
const SOURCE_COMMENT_LINE_RE =
  /^[ \t]*<!--\s*sources:\s*[^>]*?-->[ \t]*\r?\n?/gm;
const SOURCE_COMMENT_INLINE_RE = /<!--\s*sources:\s*[^>]*?-->/g;

/**
 * Strip any legacy ``<!-- sources: ... -->`` HTML comments out of a
 * SBAR markdown body. Kept exported so other markdown surfaces
 * (e.g. side-by-side diff viewers) can use the same cleanup. New
 * pipelines should not need this - they should pass
 * ``backgroundParts`` instead.
 */
export function stripSourceComments(md: string): string {
  if (!md) return md;
  return md
    .replace(SOURCE_COMMENT_LINE_RE, "")
    .replace(SOURCE_COMMENT_INLINE_RE, "");
}

/**
 * Split a SBAR Markdown payload (``# SBAR\n## Situation\n...\n##
 * Background\n...``) into one entry per stage. Anything before the
 * first matched heading is dropped. Sections are returned in canonical
 * SBAR order. If no headings match, returns an empty array - callers
 * should fall back to rendering the raw Markdown as a single block.
 */
export function splitFinalSbar(md: string): SbarSection[] {
  const lines = (md ?? "").split(/\r?\n/);
  const out = new Map<SbarStageName, string[]>();
  let current: SbarStageName | null = null;
  for (const line of lines) {
    const heading = line.match(/^##\s+(.+?)\s*$/);
    if (heading) {
      const name = heading[1].trim().toLowerCase();
      const stage = (SECTION_ORDER as string[]).find(
        (s) => s === name,
      ) as SbarStageName | undefined;
      if (stage) {
        current = stage;
        if (!out.has(stage)) out.set(stage, []);
        continue;
      }
      current = null;
      continue;
    }
    if (current) out.get(current)!.push(line);
  }
  return SECTION_ORDER.filter((s) => out.has(s)).map((stage) => ({
    stage,
    body: (out.get(stage) || []).join("\n").trim(),
  }));
}

const ADVISORY_DISCLAIMER =
  "AI-generated summary. Clinician review required before acting on this " +
  "content. This is a decision support aid, it does not replace your " +
  "clinical judgement.";

export interface SbarFinalViewProps {
  /** SBAR Markdown payload from the pipeline. */
  markdown: string;
  /** Per-partition Background source-record summaries (typically
   *  threaded through from useSbarStream's ``backgroundParts`` or
   *  the GET /sbar/assessments/{id} ``background_parts`` field).
   *  When present, each entry feeds the per-section
   *  "Show source records" disclosure on the Background card. */
  backgroundParts?: SbarBackgroundPart[];
  /**
   * @deprecated No longer controls any visible element. The advisory
   *   disclaimer is always shown per MHRA labelling requirements.
   */
  testOnly?: boolean;
  /** Compact spacing/typography for embedding in narrow drawers. */
  dense?: boolean;
  /** data-testid suffix for embedders that render multiple views. */
  testIdPrefix?: string;
  /** Referral completeness findings from the pipeline quality check.
   *  When present, a percentage pill is shown in the Background
   *  section header with a tooltip listing present/missing fields. */
  completenessFinding?: CompletenessFinding | null;
}

export type { CompletenessFinding };

interface SectionSourcesPanelProps {
  testIdPrefix: string;
  stage: SbarStageName;
  parts: SbarBackgroundPart[];
  ink: string;
}

function _formatRecordRange(start: number, end: number): string {
  if (start <= 0 || end <= 0) return "no records";
  if (start === end) return `record ${start}`;
  return `records ${start}-${end}`;
}

const UUID_PREFIX_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:/i;

/**
 * Strip the leading patient UUID from a composite source ID and present
 * the remainder in a readable form.
 *
 * e.g. "e337c274-...:upper_gi_form_001:encounter"
 *   -> "upper_gi_form_001 (encounter)"
 *
 * IDs that do not start with a UUID are returned unchanged.
 */
function _formatSourceId(id: string): string {
  const stripped = id.replace(UUID_PREFIX_RE, "");
  if (stripped === id) return id;
  const parts = stripped.split(":");
  if (parts.length >= 2) {
    const label = parts.slice(0, -1).join(":");
    const type = parts[parts.length - 1];
    return `${label} (${type})`;
  }
  return stripped;
}

function _partLabel(part: SbarBackgroundPart): string {
  const range = _formatRecordRange(
    part.recordRange?.[0] ?? 0,
    part.recordRange?.[1] ?? 0,
  );
  return `Part ${part.index} of ${part.total} -- ${range}`;
}

/**
 * Per-section "Show source records" disclosure. The source IDs are
 * audit-only metadata - reviewers only see them when they explicitly
 * ask, so the panel starts collapsed and is hidden entirely when
 * the section has no structured source data.
 */
function SectionSourcesPanel({
  testIdPrefix,
  stage,
  parts,
  ink,
}: SectionSourcesPanelProps) {
  const [open, setOpen] = useState(false);
  if (parts.length === 0) return null;
  const totalIds = parts.reduce((acc, p) => acc + (p.sourceIds?.length ?? 0), 0);
  if (totalIds === 0) return null;
  return (
    <Box
      sx={{ px: 1.75, pb: 1, pt: 0.25 }}
      data-testid={`${testIdPrefix}-section-${stage}-sources`}
    >
      <Link
        component="button"
        type="button"
        underline="hover"
        onClick={() => setOpen((v) => !v)}
        sx={{
          color: ink,
          fontSize: "0.75rem",
          fontWeight: 600,
          letterSpacing: 0.2,
        }}
        aria-expanded={open}
        data-testid={`${testIdPrefix}-section-${stage}-sources-toggle`}
      >
        {open
          ? `Hide source records (${totalIds})`
          : `Show source records (${totalIds})`}
      </Link>
      <Collapse in={open} unmountOnExit>
        <Stack spacing={1} sx={{ mt: 1 }}>
          {parts.map((p, i) => (
            <Box
              key={`${stage}-sources-${i}`}
              data-testid={`${testIdPrefix}-section-${stage}-sources-part-${i}`}
            >
              <Typography
                variant="caption"
                sx={{
                  color: "text.secondary",
                  display: "block",
                  mb: 0.5,
                }}
              >
                {_partLabel(p)}
                {p.status === "failed"
                  ? " -- this part did not finish"
                  : ""}
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={0.5}>
                {(p.sourceIds ?? []).map((id) => (
                  <Chip
                    key={id}
                    size="small"
                    variant="outlined"
                    label={_formatSourceId(id)}
                    title={id}
                    sx={{ height: 20, fontSize: "0.65rem" }}
                  />
                ))}
              </Stack>
            </Box>
          ))}
        </Stack>
      </Collapse>
    </Box>
  );
}

/**
 * Themed-card stack for the SBAR (final) Markdown payload. Pure
 * presentational - no network calls, no hooks beyond rendering the
 * MarkdownEditor in view mode.
 *
 * Source-record IDs are NOT parsed out of the markdown body. The
 * pipeline used to embed ``<!-- sources: ... -->`` HTML comments
 * after each ``### Part i of N`` heading; that leaked the raw UUIDs
 * into the rendered output because the Tiptap markdown view runs
 * with ``html: false``. Source IDs are now passed in as a typed
 * ``backgroundParts`` prop (sourced from the SSE
 * ``sbar_stage_completed.parts`` field or
 * ``GET /sbar/assessments/{id}.background_parts``) and rendered
 * behind an explicit "Show source records" disclosure on the
 * Background card. ``stripSourceComments`` is still applied to the
 * markdown so legacy persisted Assessments do not leak the comments
 * either.
 */
export function SbarFinalView({
  markdown,
  backgroundParts = [],
  testOnly: _testOnly = true,
  dense = false,
  testIdPrefix = "sbar-final",
  completenessFinding,
}: SbarFinalViewProps) {
  const sections = splitFinalSbar(markdown ?? "");
  const fontSize = dense ? "0.85rem" : "0.9rem";
  const headerPadding = dense ? "6px 10px" : "8px 14px";
  const bodyPadding = dense ? "6px 10px" : "8px 14px";

  const cleanedMarkdown = useMemo(
    () => stripSourceComments(markdown ?? ""),
    [markdown],
  );

  return (
    <Box
      data-testid={`${testIdPrefix}-content`}
      sx={{ display: "flex", flexDirection: "column", gap: dense ? 1 : 1.5 }}
    >
      <Alert
        severity="info"
        data-testid={`${testIdPrefix}-advisory-disclaimer`}
        sx={{ fontSize: "0.78rem", py: 0.5, alignItems: "flex-start" }}
      >
        {ADVISORY_DISCLAIMER}
      </Alert>

      {sections.length === 0 && markdown ? (
        <Box
          sx={{
            "& .md-editor": {
              border: "1px solid",
              borderColor: "divider",
            },
          }}
        >
          <MarkdownEditor
            mode="view"
            initialContent={cleanedMarkdown}
            minHeight={0}
          />
          <SectionSourcesPanel
            testIdPrefix={testIdPrefix}
            stage="background"
            parts={backgroundParts}
            ink="#475569"
          />
        </Box>
      ) : (
        sections.map(({ stage, body }) => {
          const theme = STAGE_THEME[stage];
          const cleanBody = stripSourceComments(body);
          const partsForStage =
            stage === "background" ? backgroundParts : [];
          return (
            <Box
              key={`final-${stage}`}
              data-testid={`${testIdPrefix}-section-${stage}`}
              sx={{
                borderRadius: 1.5,
                overflow: "hidden",
                border: "1px solid",
                borderColor: "divider",
                borderLeft: `4px solid ${theme.accent}`,
                bgcolor: "background.paper",
              }}
            >
              <Box sx={{ padding: headerPadding, bgcolor: theme.tint }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between">
                  <Typography
                    variant="subtitle2"
                    sx={{ color: theme.ink, fontWeight: 700 }}
                  >
                    {STAGE_LABELS[stage]}
                  </Typography>
                  {stage === "background" && completenessFinding && (
                    <CompletenessPill
                      finding={completenessFinding}
                      testIdPrefix={testIdPrefix}
                    />
                  )}
                </Stack>
              </Box>
              <Box
                sx={{
                  "& .md-editor": {
                    border: "none",
                    background: "transparent",
                  },
                  "& .md-editor .tiptap": {
                    padding: bodyPadding,
                    fontSize,
                  },
                }}
              >
                <MarkdownEditor
                  mode="view"
                  initialContent={cleanBody}
                  minHeight={0}
                />
              </Box>
              <SectionSourcesPanel
                testIdPrefix={testIdPrefix}
                stage={stage}
                parts={partsForStage}
                ink={theme.ink}
              />
            </Box>
          );
        })
      )}

      {markdown === "" || markdown == null ? (
        <Typography
          variant="body2"
          color="text.secondary"
          data-testid={`${testIdPrefix}-empty`}
        >
          No SBAR content yet.
        </Typography>
      ) : null}
    </Box>
  );
}

export interface SbarFinalDialogProps extends SbarFinalViewProps {
  open: boolean;
  onClose: () => void;
  /** Header above the cards. Defaults to ``SBAR (final)``. */
  title?: string;
  /** Optional subtitle (e.g. ``run 35c0ac2f -- assessment f72b123f``). */
  subtitle?: string;
  /** Show the "Copy Markdown" action in the dialog footer. */
  showCopy?: boolean;
}

/**
 * Modal wrapper for ``SbarFinalView``. Embedders typically open this
 * from a "View SBAR" button once a pipeline run has completed, but it
 * can be used standalone with any SBAR Markdown payload.
 */
export function SbarFinalDialog({
  open,
  onClose,
  title = "SBAR (final)",
  subtitle,
  showCopy = true,
  ...viewProps
}: SbarFinalDialogProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(viewProps.markdown ?? "");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Ignore clipboard failures - browser permission denied etc.
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      scroll="paper"
      data-testid="sbar-final-dialog"
    >
      <DialogTitle sx={{ pr: 6 }}>
        <Typography variant="h6" component="span">
          {title}
        </Typography>
        {subtitle && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.5 }}
          >
            {subtitle}
          </Typography>
        )}
        <IconButton
          aria-label="Close"
          onClick={onClose}
          size="small"
          sx={{ position: "absolute", right: 8, top: 8 }}
          data-testid="sbar-final-dialog-close"
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <SbarFinalView {...viewProps} testOnly={false} />
      </DialogContent>
      <DialogActions>
        {showCopy && (
          <Button
            startIcon={<ContentCopyIcon />}
            onClick={handleCopy}
            data-testid="sbar-final-dialog-copy"
          >
            {copied ? "Copied" : "Copy Markdown"}
          </Button>
        )}
        <Button onClick={onClose} variant="contained">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
