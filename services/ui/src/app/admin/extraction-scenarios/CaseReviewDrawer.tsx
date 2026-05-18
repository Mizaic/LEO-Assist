/**
 * Case Review Dialog -- shows a scenario's Markdown and expected phrases,
 * and lets a reviewer approve the case.
 *
 * Layout: modal dialog.
 *   Left:  raw markdown_body exactly as sent to the extraction pipeline
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
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { approveScenario, getScenario } from "./api";
import type { ExtractionScenarioDetail } from "./types";

interface Props {
  caseId: string | null;
  open: boolean;
  onClose: () => void;
  onApproved: () => void;
}

interface ValueInfo {
  value?: string;
  unit?: string;
}

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

function RawMarkdownViewer({ body }: { body: string }) {
  return (
    <Box
      component="pre"
      sx={{
        p: 1.5,
        bgcolor: "background.default",
        borderRadius: 1,
        border: "1px solid",
        borderColor: "divider",
        color: "text.primary",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        fontSize: "0.78rem",
        lineHeight: 1.55,
        m: 0,
        overflowX: "auto",
        overflowY: "auto",
        maxHeight: "calc(100vh - 240px)",
        whiteSpace: "pre",
      }}
      data-testid="markdown-viewer"
      data-view-mode="raw"
    >
      {body}
    </Box>
  );
}

// LONG FUNCTION: dialog coordinates fetch, approve, markdown, phrase table,
// and approval footer for one review workflow.
export default function CaseReviewDrawer({ caseId, open, onClose, onApproved }: Props) {
  const [detail, setDetail] = useState<ExtractionScenarioDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [mustNotOpen, setMustNotOpen] = useState(false);

  useEffect(() => {
    if (!open || !caseId) return;
    setLoading(true);
    setError(null);
    setDetail(null);
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
  const valueLookup = detail
    ? buildValueLookup(detail)
    : new Map<string, ValueInfo>();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="xl"
      scroll="paper"
      data-testid="case-review-dialog"
    >
      <DialogTitle>
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

      <DialogContent dividers>
        {loading ? (
          <Stack alignItems="center" sx={{ pt: 6 }}>
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
              gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
              gap: 3,
              flex: 1,
              minHeight: 0,
            }}
          >
          {/* Left: Markdown */}
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5, fontWeight: 600 }}>
              Raw Markdown sent to pipeline
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              This is the exact document payload from markdown_body.
            </Typography>
            {detail.notes_for_clinician_review ? (
              <Alert severity="info" sx={{ mb: 1, fontSize: "0.8rem" }}>
                {detail.notes_for_clinician_review}
              </Alert>
            ) : null}
            <RawMarkdownViewer body={detail.markdown_body} />
          </Box>

          {/* Right: Phrases + actions */}
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
              Expected phrases ({detail.expected_strings.length})
            </Typography>
            <Box
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
                overflowY: "auto",
                maxHeight: 320,
                mb: 2,
              }}
            >
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 600 }}>#</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Phrase</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Value</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {detail.expected_strings.map((phrase, i) => {
                    const value = valueLookup.get(normaliseKey(phrase));
                    return (
                      <TableRow key={i} data-testid={`expected-phrase-${i}`}>
                        <TableCell sx={{ color: "text.secondary" }}>{i + 1}</TableCell>
                        <TableCell>{phrase}</TableCell>
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
              <Box sx={{ mb: 2 }}>
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
                  onClick={() => setMustNotOpen((v) => !v)}
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
                      overflowY: "auto",
                      maxHeight: 160,
                    }}
                  >
                    <Table size="small">
                      <TableBody>
                        {detail.must_not_extract.map((phrase, i) => (
                          <TableRow key={i}>
                            <TableCell sx={{ color: "text.secondary" }}>{i + 1}</TableCell>
                            <TableCell>{phrase}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                </Collapse>
              </Box>
            ) : null}

            {/* Difficulty + phrase class chips */}
            <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mb: 2 }}>
              {detail.phrase_classes.map((c) => (
                <Chip key={c} size="small" label={c.replace(/_/g, " ")} />
              ))}
              {detail.difficulty.map((d) => (
                <Chip key={d} size="small" label={d.replace(/_/g, " ")} variant="outlined" />
              ))}
            </Stack>

            {isApproved ? (
              <Stack direction="row" alignItems="center" spacing={1}>
                <CheckCircleOutlineIcon color="success" fontSize="small" />
                <Typography variant="body2" color="success.main">
                  Approved by {detail.reviewed_by ?? "unknown"}
                </Typography>
              </Stack>
            ) : null}
          </Box>
          </Box>
        ) : null}
      </DialogContent>

      <DialogActions sx={{ justifyContent: "space-between", px: 3 }}>
        <Typography variant="caption" color="text.secondary">
          Approving means the expected phrases and values look correct.
        </Typography>
        <Stack direction="row" spacing={1}>
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
