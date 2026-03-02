"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TermSearch from "@/components/TermSearch";
import type { TermSearchResult } from "@/lib/types";

// -- Types -------------------------------------------------------------------

export interface ReviewItem {
  id: string;
  kind: "coding" | "hitl";
  entityText: string;
  entityLabel: string;
  count: number;
  confidence: number | null;
  uncoded: boolean;
  question: string;
  explanation: string;
  taskType?: string;
  reason?: string;
}

type TypeLabel = { text: string; color: "warning" | "info" | "error" | "default" };

function typeLabel(item: ReviewItem): TypeLabel {
  if (item.kind === "coding") {
    if (item.uncoded) return { text: "Missing code", color: "warning" };
    return { text: "Check this code", color: "info" };
  }
  const map: Record<string, TypeLabel> = {
    exclusion_conflict: { text: "Inclusion check", color: "error" },
    peer_review: { text: "Peer review", color: "info" },
    classification: { text: "Classification check", color: "info" },
  };
  return map[item.taskType ?? ""] ?? { text: "Review needed", color: "default" };
}

// -- Helpers for plain-language questions ------------------------------------

export function buildQuestion(item: ReviewItem): string {
  if (item.kind === "coding" && item.uncoded) {
    return `What code should we use for '${item.entityText}'?`;
  }
  if (item.kind === "coding") {
    return `Is the code for '${item.entityText}' correct?`;
  }
  if (item.taskType === "exclusion_conflict") {
    return "Should this patient be in the measure?";
  }
  return "Does this look right to you?";
}

export function buildExplanation(item: ReviewItem): string {
  if (item.kind === "coding" && item.uncoded) {
    return (
      `We found '${item.entityText}' in ${item.count} patient ` +
      `${item.count === 1 ? "record" : "records"} but could not match ` +
      `it to a clinical code. Search for the right one, or skip if ` +
      `you are not sure.`
    );
  }
  if (item.kind === "coding") {
    const pct = item.confidence != null ? Math.round(item.confidence * 100) : 0;
    return (
      `We matched '${item.entityText}' to a code but our system is ` +
      `only ${pct}% sure. This appears in ${item.count} ` +
      `${item.count === 1 ? "record" : "records"}. ` +
      `Please check if this is right.`
    );
  }
  return item.reason ?? "Please review this item.";
}

// -- Card component ----------------------------------------------------------

interface Props {
  item: ReviewItem;
  onResolveCoding: (item: ReviewItem, result: TermSearchResult) => void;
  onResolveHitl: (item: ReviewItem, status: "resolved" | "dismissed") => void;
  onSkip: () => void;
  busy: boolean;
}

export default function ReviewCard({
  item,
  onResolveCoding,
  onResolveHitl,
  onSkip,
  busy,
}: Props) {
  const [termOpen, setTermOpen] = useState(false);
  const label = typeLabel(item);

  return (
    <>
      <Card sx={{ animation: "cardIn 0.2s ease" }}>
        <CardContent sx={{ p: 3 }}>
          <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 2 }}>
            <Chip label={label.text} color={label.color} size="small" />
            {item.count > 1 && (
              <Chip
                label={`${item.count} records`}
                size="small"
                variant="outlined"
              />
            )}
            {item.entityLabel && (
              <Chip
                label={item.entityLabel.replace(/_/g, " ")}
                size="small"
                variant="outlined"
                color="primary"
              />
            )}
          </Stack>

          <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
            {item.question}
          </Typography>
          <Typography
            variant="body1"
            color="text.secondary"
            sx={{ mb: 3, lineHeight: 1.6 }}
          >
            {item.explanation}
          </Typography>

          {/* Actions */}
          {item.kind === "coding" ? (
            <CodingActions
              item={item}
              busy={busy}
              onSearch={() => setTermOpen(true)}
              onSkip={onSkip}
            />
          ) : (
            <HitlActions
              item={item}
              busy={busy}
              onResolve={onResolveHitl}
              onSkip={onSkip}
            />
          )}
        </CardContent>
      </Card>

      {/* Terminology search dialog */}
      {termOpen && (
        <TermSearch
          initialQuery={item.entityText}
          onSelect={(r) => {
            setTermOpen(false);
            onResolveCoding(item, r);
          }}
          onClose={() => setTermOpen(false)}
          onCorrection={() => {}}
        />
      )}
    </>
  );
}

// -- Sub-components ----------------------------------------------------------

function CodingActions({
  item,
  busy,
  onSearch,
  onSkip,
}: {
  item: ReviewItem;
  busy: boolean;
  onSearch: () => void;
  onSkip: () => void;
}) {
  return (
    <Stack direction="row" gap={1}>
      <Button
        variant="contained"
        onClick={onSearch}
        disabled={busy}
        fullWidth
      >
        {item.uncoded ? "Search for the right code" : "Search for a better code"}
      </Button>
      <Button variant="outlined" onClick={onSkip} disabled={busy}>
        Skip
      </Button>
    </Stack>
  );
}

function HitlActions({
  item,
  busy,
  onResolve,
  onSkip,
}: {
  item: ReviewItem;
  busy: boolean;
  onResolve: (item: ReviewItem, status: "resolved" | "dismissed") => void;
  onSkip: () => void;
}) {
  return (
    <Stack direction="row" gap={1}>
      <Button
        variant="contained"
        color="success"
        onClick={() => onResolve(item, "resolved")}
        disabled={busy}
        fullWidth
      >
        Approve
      </Button>
      <Button
        variant="outlined"
        color="error"
        onClick={() => onResolve(item, "dismissed")}
        disabled={busy}
        fullWidth
      >
        Dismiss
      </Button>
      <Button variant="outlined" onClick={onSkip} disabled={busy}>
        Skip
      </Button>
    </Stack>
  );
}
