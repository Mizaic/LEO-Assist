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
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { useState } from "react";
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

export interface SbarFinalViewProps {
  /** SBAR Markdown payload from the pipeline. */
  markdown: string;
  /** Test-only banner. Defaults to true so embedders cannot
   *  accidentally present this view as an authoritative record. */
  testOnly?: boolean;
  /** Compact spacing/typography for embedding in narrow drawers. */
  dense?: boolean;
  /** data-testid suffix for embedders that render multiple views. */
  testIdPrefix?: string;
}

/**
 * Themed-card stack for the SBAR (final) Markdown payload. Pure
 * presentational - no network calls, no hooks beyond rendering the
 * MarkdownEditor in view mode.
 */
export function SbarFinalView({
  markdown,
  testOnly = true,
  dense = false,
  testIdPrefix = "sbar-final",
}: SbarFinalViewProps) {
  const sections = splitFinalSbar(markdown ?? "");
  const fontSize = dense ? "0.85rem" : "0.9rem";
  const headerPadding = dense ? "6px 10px" : "8px 14px";
  const bodyPadding = dense ? "6px 10px" : "8px 14px";

  return (
    <Box
      data-testid={`${testIdPrefix}-content`}
      sx={{ display: "flex", flexDirection: "column", gap: dense ? 1 : 1.5 }}
    >
      {testOnly && (
        <Chip
          size="small"
          color="success"
          label="Test only -- not for clinical use"
          sx={{ height: 20, fontSize: "0.65rem", alignSelf: "flex-start" }}
          data-testid={`${testIdPrefix}-test-only-banner`}
        />
      )}

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
            initialContent={markdown}
            minHeight={0}
          />
        </Box>
      ) : (
        sections.map(({ stage, body }) => {
          const theme = STAGE_THEME[stage];
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
                <Typography
                  variant="subtitle2"
                  sx={{ color: theme.ink, fontWeight: 700 }}
                >
                  {STAGE_LABELS[stage]}
                </Typography>
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
                  initialContent={body}
                  minHeight={0}
                />
              </Box>
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
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography variant="h6" component="span">
            {title}
          </Typography>
          {viewProps.testOnly !== false && (
            <Chip
              size="small"
              color="success"
              label="Test only -- not for clinical use"
              sx={{ height: 20, fontSize: "0.65rem" }}
            />
          )}
        </Stack>
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
