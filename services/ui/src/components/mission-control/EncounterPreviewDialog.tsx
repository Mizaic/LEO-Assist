"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { EncounterCodedLink, EncounterListItem } from "@/lib/missionControlApi";
import { ASSERTION_CHIP } from "@/lib/types";

type ChipColor = "default" | "primary" | "secondary" | "error" | "info" | "success" | "warning";

function chipPropsForAssertion(assertionRaw: string): {
  color: ChipColor;
  variant: "filled" | "outlined";
} {
  const key = assertionRaw.trim().toLowerCase();
  const meta = ASSERTION_CHIP[key];
  if (!meta) return { color: "default", variant: "outlined" };
  const strong = meta.color === "error" || meta.color === "warning";
  return { color: meta.color, variant: strong ? "filled" : "outlined" };
}

function formatDateLong(dateStr: string | null): string {
  if (!dateStr) return "Unknown date";
  return new Date(dateStr).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function toOneLine(value: string | null | undefined): string {
  return (value || "").replace(/\s+/g, " ").trim();
}

function codedLinkTooltip(link: EncounterCodedLink): string {
  const lines: string[] = [];
  lines.push(`Concept: ${link.concept_id}`);
  lines.push(`Assertion: ${link.assertion || "present"}`);
  if (typeof link.confidence === "number") {
    lines.push(`Confidence: ${Math.round(link.confidence * 100)}%`);
  }
  if (link.source) lines.push(`Source: ${link.source}`);
  if (link.domain) lines.push(`Domain: ${link.domain}`);
  if (link.model_name) {
    lines.push(
      `Model: ${link.model_name}${link.model_version ? ` v${link.model_version}` : ""}`
    );
  }
  if (link.run_id) lines.push(`Run: ${link.run_id}`);
  const evidence = toOneLine(link.evidence_sentence || link.evidence);
  if (evidence) lines.push(`Evidence: ${evidence}`);
  if (
    typeof link.sentence_index === "number" ||
    typeof link.evidence_start === "number" ||
    typeof link.evidence_end === "number"
  ) {
    lines.push(
      `Span: s${link.sentence_index ?? "?"} [${link.evidence_start ?? "?"}, ${link.evidence_end ?? "?"}]`
    );
  }
  return lines.join("\n");
}

interface Props {
  item: EncounterListItem | null;
  codedLinks: EncounterCodedLink[];
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

function CodedTermsSkeleton() {
  return (
    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
      {[90, 115, 80, 130, 75, 100].map((w) => (
        <Skeleton key={w} width={w} height={28} sx={{ borderRadius: 4 }} />
      ))}
    </Stack>
  );
}

export default function EncounterPreviewDialog({ item, codedLinks, loading, error, onClose }: Props) {
  if (!item) return null;

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ pb: 0.5 }}>
        <Typography variant="h6" component="span">
          Encounter detail
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
          {formatDateLong(item.encounter_date)} &mdash; Patient{" "}
          <Box component="span" sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
            {item.patient_id}
          </Box>
        </Typography>
      </DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2.5}>
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            <Chip
              size="small"
              label={`ID: ${item.encounter_id}`}
              variant="outlined"
              sx={{ fontFamily: "monospace", fontSize: "0.72rem" }}
            />
            <Chip size="small" label={`Match: ${item.match_type}`} variant="outlined" />
            <Chip
              size="small"
              label={`${item.coded_count} coded term${item.coded_count !== 1 ? "s" : ""}`}
              color={item.coded_count > 0 ? "success" : "default"}
              variant={item.coded_count > 0 ? "filled" : "outlined"}
            />
          </Stack>

          <Divider />

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
              Coded terms
            </Typography>
            {loading && <CodedTermsSkeleton />}
            {error && (
              <Typography variant="body2" color="error">
                {error}
              </Typography>
            )}
            {!loading && !error && codedLinks.length === 0 && (
              <Typography variant="body2" color="text.secondary">
                No coded terms recorded for this encounter.
              </Typography>
            )}
            {!loading && codedLinks.length > 0 && (
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {codedLinks.map((link, index) => {
                  const term = (link.term || link.concept_id || "unknown").trim();
                  const assertion = (link.assertion || "present").trim();
                  const { color, variant } = chipPropsForAssertion(assertion);
                  return (
                    <Tooltip
                      key={`${item.encounter_id}-coded-${index}-${link.concept_id}`}
                      title={
                        <Typography
                          component="pre"
                          sx={{ m: 0, fontFamily: "monospace", fontSize: "0.72rem", whiteSpace: "pre-wrap" }}
                        >
                          {codedLinkTooltip(link)}
                        </Typography>
                      }
                      placement="top"
                      arrow
                    >
                      <Chip
                        size="small"
                        label={`${term} (${assertion})`}
                        color={color}
                        variant={variant}
                      />
                    </Tooltip>
                  );
                })}
              </Stack>
            )}
          </Box>

          <Divider />

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
              Encounter text
            </Typography>
            <Paper
              variant="outlined"
              sx={{ p: 2, maxHeight: 340, overflow: "auto", bgcolor: "action.hover", borderRadius: 2 }}
            >
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}>
                {item.text?.trim() || "No encounter text available."}
              </Typography>
            </Paper>
          </Box>

          {!!item.match_rationale?.length && (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                Match rationale
              </Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {item.match_rationale.map((term, idx) => (
                  <Chip
                    key={`preview-${item.encounter_id}-mr-${idx}-${term}`}
                    size="small"
                    label={term}
                    variant="outlined"
                  />
                ))}
              </Stack>
            </Box>
          )}
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
