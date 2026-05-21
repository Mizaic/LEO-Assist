/**
 * Case Review Dialog -- shows a scenario's Markdown and expected phrases,
 * and lets a reviewer approve the case.
 *
 * Layout: modal dialog, two columns on large screens.
 *   Left:  clinical document (rendered Markdown, optional raw source toggle)
 *   Right: expected_strings table with value/unit where available
 *
 * Atlas: DI-1B3B5375, DI-B492CAFD, DO-416BA91D, VT-24D7A846.
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import MarkdownEditor from "@/components/markdown-editor/MarkdownEditor";

import { approveScenario, getScenario } from "./api";
import { phraseTag, phraseText } from "./phraseHelpers";
import type { ExtractionScenarioDetail } from "./types";

interface Props {
  caseId: string | null;
  open: boolean;
  onClose: () => void;
  onApproved: () => void;
  onEdit?: (caseId: string) => void;
}

interface ValueInfo {
  value?: string;
  unit?: string;
}

type DocumentViewMode = "rendered" | "raw";

function normaliseKey(value: string): string {
  return value.trim().toLowerCase();
}

function buildValueLookup(detail: ExtractionScenarioDetail): Map<string, ValueInfo> {
  const lookup = new Map<string, ValueInfo>();
  for (const obs of detail.expected_observables ?? []) {
    lookup.set(normaliseKey(obs.text), {
      value: obs.value,
      unit: obs.unit,
    });
  }

  const blood = detail.blood_results;
  if (blood && !Array.isArray(blood) && Array.isArray(blood.results)) {
    for (const result of blood.results) {
      lookup.set(normaliseKey(result.test_name), {
        value: result.value == null ? undefined : String(result.value),
        unit: result.unit,
      });
    }
  }
  return lookup;
}

function RawMarkdownPane({ body }: { body: string }) {
  return (
    <Box
      component="pre"
      sx={{
        p: 1.5,
        m: 0,
        height: "100%",
        bgcolor: "background.default",
        color: "text.primary",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        fontSize: "0.78rem",
        lineHeight: 1.55,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        overflow: "auto",
      }}
      data-testid="markdown-viewer"
      data-view-mode="raw"
    >
      {body}
    </Box>
  );
}

function RenderedMarkdownPane({ body }: { body: string }) {
  return (
    <Box
      data-testid="markdown-viewer"
      data-view-mode="rendered"
      sx={{
        "& .md-editor": { border: "none", borderRadius: 0 },
        "& .md-editor .tiptap": { minHeight: 0 },
      }}
    >
      <MarkdownEditor
        key={body}
        initialContent={body}
        mode="view"
        minHeight={0}
        className="extraction-scenario-markdown"
      />
    </Box>
  );
}

interface DocumentPaneProps {
  body: string;
  viewMode: DocumentViewMode;
  onViewModeChange: (mode: DocumentViewMode) => void;
  clinicianNote: string | null;
}

function DocumentPane({
  body,
  viewMode,
  onViewModeChange,
  clinicianNote,
}: DocumentPaneProps) {
  return (
    <Stack sx={{ height: "100%", minHeight: 0, minWidth: 0 }} spacing={1}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        alignItems={{ xs: "flex-start", sm: "center" }}
        justifyContent="space-between"
        spacing={1}
      >
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            Clinical document
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Same markdown_body payload sent to the extraction pipeline.
          </Typography>
        </Box>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={viewMode}
          onChange={(_, next: DocumentViewMode | null) => {
            if (next) onViewModeChange(next);
          }}
          aria-label="Document view mode"
          data-testid="markdown-view-toggle"
        >
          <ToggleButton value="rendered" data-testid="markdown-view-rendered">
            Rendered
          </ToggleButton>
          <ToggleButton value="raw" data-testid="markdown-view-raw">
            Raw source
          </ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {clinicianNote ? (
        <Alert severity="info" sx={{ fontSize: "0.8rem", flexShrink: 0 }}>
          {clinicianNote}
        </Alert>
      ) : null}

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          overflow: "auto",
          bgcolor: "background.paper",
        }}
        data-testid="clinical-document-panel"
      >
        {viewMode === "rendered" ? (
          <RenderedMarkdownPane body={body} />
        ) : (
          <RawMarkdownPane body={body} />
        )}
      </Box>
    </Stack>
  );
}

interface PhrasesPaneProps {
  detail: ExtractionScenarioDetail;
  valueLookup: Map<string, ValueInfo>;
  mustNotOpen: boolean;
  onToggleMustNot: () => void;
}

function PhrasesPane({
  detail,
  valueLookup,
  mustNotOpen,
  onToggleMustNot,
}: PhrasesPaneProps) {
  const isApproved = detail.review_status === "approved";

  return (
    <Stack sx={{ height: "100%", minHeight: 0, minWidth: 0 }} spacing={1.5}>
      <Typography variant="subtitle2" sx={{ fontWeight: 600, flexShrink: 0 }}>
        Expected phrases ({detail.expected_strings.length})
      </Typography>

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          overflow: "auto",
        }}
        data-testid="expected-phrases-panel"
      >
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, width: 48 }}>#</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Phrase</TableCell>
              <TableCell sx={{ fontWeight: 600, width: 120 }}>Value</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {detail.expected_strings.map((phrase, i) => {
              const label = phraseText(phrase);
              const tag = phraseTag(phrase);
              const value = valueLookup.get(normaliseKey(label));
              return (
                <TableRow key={i} data-testid={`expected-phrase-${i}`}>
                  <TableCell sx={{ color: "text.secondary" }}>{i + 1}</TableCell>
                  <TableCell sx={{ wordBreak: "break-word" }}>
                    {label}
                    {tag && (
                      <Typography component="span" variant="caption" sx={{ ml: 1, color: "text.secondary" }}>
                        ({tag})
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell data-testid={`expected-value-${i}`}>
                    {value?.value
                      ? `${value.value} ${value.unit ?? ""}`.trim()
                      : "-"}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Box>

      {detail.must_not_extract.length > 0 ? (
        <Box sx={{ flexShrink: 0 }}>
          <Button
            size="small"
            variant="text"
            endIcon={
              <ExpandMoreIcon
                sx={{
                  transform: mustNotOpen ? "rotate(180deg)" : "none",
                  transition: "transform 0.2s",
                }}
              />
            }
            onClick={onToggleMustNot}
            data-testid="must-not-extract-toggle"
          >
            Must not extract ({detail.must_not_extract.length})
          </Button>
          <Collapse in={mustNotOpen}>
            <Box
              sx={{
                border: "1px solid",
                borderColor: "warning.main",
                borderRadius: 1,
                mt: 1,
                maxHeight: 160,
                overflow: "auto",
              }}
            >
              <Table size="small">
                <TableBody>
                  {detail.must_not_extract.map((phrase, i) => (
                    <TableRow key={i}>
                      <TableCell sx={{ color: "text.secondary", width: 48 }}>
                        {i + 1}
                      </TableCell>
                      <TableCell sx={{ wordBreak: "break-word" }}>{phrase}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </Collapse>
        </Box>
      ) : null}

      <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ flexShrink: 0 }}>
        {detail.phrase_classes.map((c) => (
          <Chip key={c} size="small" label={c.replace(/_/g, " ")} />
        ))}
        {detail.difficulty.map((d) => (
          <Chip key={d} size="small" label={d.replace(/_/g, " ")} variant="outlined" />
        ))}
      </Stack>

      {isApproved ? (
        <Stack direction="row" alignItems="center" spacing={1} sx={{ flexShrink: 0 }}>
          <CheckCircleOutlineIcon color="success" fontSize="small" />
          <Typography variant="body2" color="success.main">
            Approved by {detail.reviewed_by ?? "unknown"}
          </Typography>
        </Stack>
      ) : null}
    </Stack>
  );
}

// LONG FUNCTION: dialog coordinates fetch, approve, and two-pane review layout.
export default function CaseReviewDrawer({
  caseId,
  open,
  onClose,
  onApproved,
  onEdit,
}: Props) {
  const [detail, setDetail] = useState<ExtractionScenarioDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [mustNotOpen, setMustNotOpen] = useState(false);
  const [documentViewMode, setDocumentViewMode] = useState<DocumentViewMode>("rendered");

  useEffect(() => {
    if (!open || !caseId) return;
    setLoading(true);
    setError(null);
    setDetail(null);
    setDocumentViewMode("rendered");
    getScenario(caseId)
      .then(setDetail)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Could not load this case.");
      })
      .finally(() => setLoading(false));
  }, [open, caseId]);

  const handleApprove = useCallback(async () => {
    if (!caseId) return;
    setApproving(true);
    setError(null);
    try {
      await approveScenario(caseId);
      onApproved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not approve this case.");
    } finally {
      setApproving(false);
    }
  }, [caseId, onApproved]);

  const isApproved = detail?.review_status === "approved";
  const valueLookup = detail ? buildValueLookup(detail) : new Map<string, ValueInfo>();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="xl"
      scroll="paper"
      data-testid="case-review-dialog"
      slotProps={{
        paper: {
          sx: {
            display: "flex",
            flexDirection: "column",
            height: { xs: "100%", sm: "min(92vh, 960px)" },
            maxHeight: "92vh",
          },
        },
      }}
    >
      <DialogTitle sx={{ flexShrink: 0 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
              {caseId ?? "Case review"}
            </Typography>
            {detail ? (
              <Typography variant="caption" color="text.secondary">
                {detail.site.replace(/_/g, " ")} &middot; {detail.format}
              </Typography>
            ) : null}
          </Box>
          <IconButton
            onClick={onClose}
            size="small"
            aria-label="Close review dialog"
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
      </DialogTitle>

      <Divider />

      <DialogContent
        dividers
        sx={{
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          p: { xs: 2, md: 2.5 },
        }}
      >
        {loading ? (
          <Stack alignItems="center" justifyContent="center" sx={{ flex: 1 }}>
            <CircularProgress size={28} />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
              Loading case...
            </Typography>
          </Stack>
        ) : error ? (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        ) : detail ? (
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.15fr) minmax(0, 0.85fr)" },
              gap: { xs: 2.5, lg: 3 },
              flex: 1,
              minHeight: 0,
              height: "100%",
            }}
          >
            <DocumentPane
              body={detail.markdown_body}
              viewMode={documentViewMode}
              onViewModeChange={setDocumentViewMode}
              clinicianNote={detail.notes_for_clinician_review}
            />
            <PhrasesPane
              detail={detail}
              valueLookup={valueLookup}
              mustNotOpen={mustNotOpen}
              onToggleMustNot={() => setMustNotOpen((v) => !v)}
            />
          </Box>
        ) : null}
      </DialogContent>

      <DialogActions sx={{ justifyContent: "space-between", px: 3, flexShrink: 0 }}>
        <Typography variant="caption" color="text.secondary">
          Approving means the expected phrases and values look correct.
        </Typography>
        <Stack direction="row" spacing={1}>
          {onEdit && caseId ? (
            <Button
              variant="outlined"
              onClick={() => onEdit(caseId)}
              data-testid="edit-scenario-button"
            >
              Edit scenario
            </Button>
          ) : null}
          <Button onClick={onClose}>Close</Button>
          {!isApproved ? (
            <Button
              variant="contained"
              color="success"
              onClick={handleApprove}
              disabled={approving || !detail}
              startIcon={
                approving ? (
                  <CircularProgress size={14} color="inherit" />
                ) : (
                  <CheckCircleOutlineIcon fontSize="small" />
                )
              }
              data-testid="approve-button"
            >
              {approving ? "Saving..." : "Approve this case"}
            </Button>
          ) : null}
        </Stack>
      </DialogActions>
    </Dialog>
  );
}
