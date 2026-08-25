/**
 * In-place extraction quality review surface for the Validation Lab.
 * Letter with live highlights on the left; structured fact editor on the right.
 *
 * Atlas trace: DI-4A012A59 / DO-E7824FED
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import LetterMarkdownView from "@/app/admin/validation-lab/LetterMarkdownView";
import { LetterMarkLegend } from "@/app/admin/validation-lab/LetterMarks";
import WorkFixPanel from "@/app/work/WorkFixPanel";
import {
  EMPTY_LETTER_COPY,
  QUALITY_SCORE_HINT,
  pauseReasonLabels,
} from "./extractionReviewCopy";
import { focusedReviewMarks } from "./extractionReviewHighlight";
import {
  FactList,
  draftExtractor,
  type DocumentQuality,
  type DraftEntity,
} from "./ExtractionReviewFacts";

interface ReviewData {
  sourceText: string;
  entities: DraftEntity[];
  quality: DocumentQuality;
  reason: string;
}

interface Props {
  taskId: string;
  open: boolean;
  onClose: () => void;
  onUnlocked: () => void;
}

// -- main component ---------------------------------------------------------

export default function ExtractionQualityReviewDialog({
  taskId,
  open,
  onClose,
  onUnlocked,
}: Props) {
  const [data, setData] = useState<ReviewData | null>(null);
  const [entities, setEntities] = useState<DraftEntity[]>([]);
  const [pickedText, setPickedText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !taskId) return;
    setError("");
    setData(null);
    fetch(`/api/operations/extraction-reviews/${taskId}`, {
      credentials: "include",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((res) => {
        if (!res.ok) throw new Error("load");
        return res.json() as Promise<Record<string, unknown>>;
      })
      .then((raw) => {
        const loaded: ReviewData = {
          sourceText: String(raw.source_text ?? ""),
          entities: Array.isArray(raw.draft_entities) ? (raw.draft_entities as DraftEntity[]) : [],
          quality: (raw.document_quality as DocumentQuality) ?? {},
          reason: String(raw.reason ?? ""),
        };
        setData(loaded);
        setEntities(loaded.entities);
        setPickedText(loaded.entities[0]?.text ?? "");
      })
      .catch(() => setError("Could not load the letter. Try again."));
  }, [open, taskId]);

  function addSelection() {
    const text = window.getSelection()?.toString().trim() ?? "";
    if (!text) return;
    setEntities((prev) =>
      prev.some((e) => e.text === text)
        ? prev
        : [...prev, { text, semantic_tag: "", assertion: "present" }],
    );
  }

  function removeEntity(text: string) {
    setEntities((prev) => prev.filter((e) => e.text !== text));
  }

  function patchEntity(text: string, patch: Partial<DraftEntity>) {
    setEntities((prev) => prev.map((e) => (e.text === text ? { ...e, ...patch } : e)));
  }

  async function unlock() {
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/operations/extraction-reviews/complete", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          task_id: taskId,
          source_text: data?.sourceText ?? "",
          reviewed_entities: entities,
          resolved_by: "validation_lab",
        }),
      });
      if (!res.ok) throw new Error("complete");
      onUnlocked();
    } catch {
      setError("Could not unlock the referral. Check the facts and try again.");
    } finally {
      setBusy(false);
    }
  }

  const focusTerm = pickedText || entities[0]?.text || "";
  const marks = focusedReviewMarks(entities, focusTerm);
  const score = data?.quality.document_quality_score ?? 0;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth={false}
      data-testid="extraction-quality-review-dialog"
      PaperProps={{
        sx: {
          width: "min(1400px, 100%)",
          height: "min(900px, calc(100vh - 32px))",
          maxWidth: "none",
          m: 2,
        },
      }}
    >
      <Stack sx={{ height: "100%", minHeight: 0 }}>
        <ReviewHeader
          reason={data?.reason ?? ""}
          qualityReasons={data?.quality.quality_reasons ?? []}
          score={score}
          loaded={Boolean(data)}
          onClose={onClose}
        />
        <Box sx={{ display: "flex", flex: 1, minHeight: 0 }}>
          <ReviewLetterPane
            sourceText={data?.sourceText ?? ""}
            marks={marks}
            focusTerm={focusTerm}
            onAddSelection={addSelection}
          />
          <ReviewFactsPane
            entities={entities}
            error={error}
            busy={busy}
            encounterText={data?.sourceText ?? ""}
            pickedText={focusTerm}
            onPick={setPickedText}
            onRemove={removeEntity}
            onPatch={patchEntity}
            onBack={onClose}
            onUnlock={() => void unlock()}
          />
        </Box>
      </Stack>
    </Dialog>
  );
}

// -- ReviewHeader -----------------------------------------------------------

function ReviewHeader({
  reason,
  qualityReasons,
  score,
  loaded,
  onClose,
}: {
  reason: string;
  qualityReasons: string[];
  score: number;
  loaded: boolean;
  onClose: () => void;
}) {
  const scorePercent = Math.round(score * 100);
  const scoreColor = score > 0.7 ? "#16A34A" : score > 0.4 ? "#D97706" : "#DC2626";
  const reasons = pauseReasonLabels(reason, qualityReasons);

  return (
    <Stack
      direction="row"
      alignItems="flex-start"
      sx={{
        px: 2,
        py: 1.5,
        borderBottom: "1px solid",
        borderColor: "divider",
        bgcolor: "#FAFAFA",
        flexShrink: 0,
      }}
    >
      <WarningAmberIcon sx={{ color: "#D97706", mr: 1.5, fontSize: 22, mt: 0.25 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="subtitle1" fontWeight={700}>
          Check paused extraction
        </Typography>
        {reasons.length ? (
          <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 0.5 }}>
            {reasons.map((label) => (
              <Typography
                key={label}
                variant="caption"
                sx={{
                  px: 1,
                  py: 0.25,
                  bgcolor: "warning.light",
                  borderRadius: "4px",
                }}
              >
                {label}
              </Typography>
            ))}
          </Stack>
        ) : null}
      </Box>
      {loaded && scorePercent > 0 ? (
        <Tooltip title={QUALITY_SCORE_HINT}>
          <Box
            sx={{
              mr: 2,
              mt: 0.25,
              px: 1.5,
              py: 0.5,
              bgcolor: `${scoreColor}18`,
              border: `1px solid ${scoreColor}`,
              borderRadius: "6px",
              flexShrink: 0,
            }}
          >
            <Typography variant="caption" fontWeight={700} sx={{ color: scoreColor }}>
              Letter score {scorePercent}%
            </Typography>
          </Box>
        </Tooltip>
      ) : null}
      <IconButton onClick={onClose} size="small" aria-label="Close review">
        <CloseIcon fontSize="small" />
      </IconButton>
    </Stack>
  );
}

// -- ReviewLetterPane -------------------------------------------------------

function ReviewLetterPane({
  sourceText,
  marks,
  focusTerm,
  onAddSelection,
}: {
  sourceText: string;
  marks: ReturnType<typeof focusedReviewMarks>;
  focusTerm: string;
  onAddSelection: () => void;
}) {
  const hasLetter = Boolean(sourceText.trim());
  const letterRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = letterRef.current?.querySelector("[data-review-focus='true']");
    if (node instanceof HTMLElement) {
      node.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [focusTerm, sourceText]);
  return (
    <Box
      sx={{
        width: { xs: "100%", md: "42%" },
        minWidth: 280,
        borderRight: "1px solid",
        borderColor: "divider",
        display: "flex",
        flexDirection: "column",
        bgcolor: "grey.50",
        minHeight: 0,
      }}
    >
      <Box
        sx={{
          px: 2,
          py: 0.75,
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "action.hover",
        }}
      >
        <Typography variant="caption" fontWeight={700} color="primary.main">
          {hasLetter
            ? focusTerm
              ? "Numbers mark each time this fact appears. Select other text to add a fact."
              : "Select any text on the letter to add it as a fact"
            : "Letter"}
        </Typography>
      </Box>
      <Box
        ref={letterRef}
        sx={{ flex: 1, overflow: "auto", p: 2, cursor: hasLetter ? "text" : "default" }}
        onMouseUp={hasLetter ? onAddSelection : undefined}
        data-testid="extraction-quality-letter"
      >
        {hasLetter ? <LetterMarkLegend marks={marks} /> : null}
        <LetterMarkdownView
          text={sourceText}
          marks={marks}
          focusTerm={focusTerm}
          emptyLabel={EMPTY_LETTER_COPY}
        />
      </Box>
    </Box>
  );
}

// -- ReviewFactsPane --------------------------------------------------------

function ReviewFactsPane({
  entities,
  error,
  busy,
  encounterText,
  pickedText,
  onPick,
  onRemove,
  onPatch,
  onBack,
  onUnlock,
}: {
  entities: DraftEntity[];
  error: string;
  busy: boolean;
  encounterText: string;
  pickedText: string;
  onPick: (text: string) => void;
  onRemove: (text: string) => void;
  onPatch: (text: string, patch: Partial<DraftEntity>) => void;
  onBack: () => void;
  onUnlock: () => void;
}) {
  const picked = entities.find((entity) => entity.text === pickedText) ?? entities[0];
  return (
    <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      {error ? (
        <Box
          sx={{
            px: 2,
            py: 1,
            bgcolor: "error.light",
            borderBottom: "1px solid",
            borderColor: "error.main",
            flexShrink: 0,
          }}
        >
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        </Box>
      ) : null}
      <Box sx={{ flex: 1, overflow: "auto", p: 2 }}>
        <FactList
          entities={entities}
          letterText={encounterText}
          pickedText={picked?.text ?? ""}
          onPick={onPick}
          onRemove={onRemove}
          onPatch={onPatch}
        />
        {picked ? (
          <WorkFixPanel
            entityText={picked.text}
            entityLabel={picked.semantic_tag}
            encounterText={encounterText}
            extractionSource={draftExtractor(picked)}
          />
        ) : null}
      </Box>
      <Stack
        direction="row"
        spacing={1}
        justifyContent="flex-end"
        sx={{
          px: 2,
          py: 1.5,
          borderTop: "1px solid",
          borderColor: "divider",
          bgcolor: "#FAFAFA",
          flexShrink: 0,
        }}
      >
        <Button onClick={onBack} disabled={busy} size="small">
          Back
        </Button>
        <Button
          variant="contained"
          onClick={onUnlock}
          disabled={busy || entities.length === 0}
          size="small"
        >
          {busy ? "Unlocking..." : "Approve and unlock"}
        </Button>
      </Stack>
    </Box>
  );
}
