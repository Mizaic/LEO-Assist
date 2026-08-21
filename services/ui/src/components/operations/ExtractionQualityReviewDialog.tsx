/**
 * In-place extraction quality review surface for the Validation Lab.
 * Letter with live highlights on the left; structured fact editor on the right.
 *
 * Atlas trace: DI-4A012A59 / DO-E7824FED
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import DeleteIcon from "@mui/icons-material/Delete";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import LetterMarkdownView from "@/app/admin/validation-lab/LetterMarkdownView";
import { LetterMarkLegend } from "@/app/admin/validation-lab/LetterMarks";
import { letterHighlightMarks } from "@/app/admin/validation-lab/letterHighlight";
import {
  assertionLabel,
  markBackground,
  markContextBar,
  markForeground,
  semanticTagLabel,
  TAG_STYLE,
} from "@/app/admin/validation-lab/letterMarkStyle";

// -- types ------------------------------------------------------------------

interface DraftEntity {
  text: string;
  semantic_tag?: string;
  assertion?: string;
}

interface DocumentQuality {
  document_quality_score?: number;
  quality_reasons?: string[];
}

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

// -- constants --------------------------------------------------------------

const REASON_LABELS: Record<string, string> = {
  low_document_quality: "Low document quality score",
  missing_entities: "No facts extracted from the letter",
  few_shot_ood: "Letter format is unlike training examples",
  manual_pause: "Manually paused for review",
};

const TAG_OPTIONS = Object.keys(TAG_STYLE);

const ASSERTION_OPTIONS: [string, string][] = [
  ["present", "Present"],
  ["historical", "Historical"],
  ["absent", "Not present"],
  ["possible", "Uncertain"],
  ["planned", "Planned"],
  ["family", "Family history"],
  ["declined", "Declined"],
];

function reasonLabel(r: string) {
  return REASON_LABELS[r] ?? r.replace(/_/g, " ");
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

  const marks = letterHighlightMarks(entities);
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
          score={score}
          loaded={Boolean(data)}
          onClose={onClose}
        />
        <Box sx={{ display: "flex", flex: 1, minHeight: 0 }}>
          <ReviewLetterPane
            sourceText={data?.sourceText ?? ""}
            marks={marks}
            onAddSelection={addSelection}
          />
          <ReviewFactsPane
            entities={entities}
            quality={data?.quality}
            error={error}
            busy={busy}
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
  score,
  loaded,
  onClose,
}: {
  reason: string;
  score: number;
  loaded: boolean;
  onClose: () => void;
}) {
  const scorePercent = Math.round(score * 100);
  const scoreColor = score > 0.7 ? "#16A34A" : score > 0.4 ? "#D97706" : "#DC2626";

  return (
    <Stack
      direction="row"
      alignItems="center"
      sx={{
        px: 2,
        py: 1.5,
        borderBottom: "1px solid",
        borderColor: "divider",
        bgcolor: "#FAFAFA",
        flexShrink: 0,
      }}
    >
      <WarningAmberIcon sx={{ color: "#D97706", mr: 1.5, fontSize: 22 }} />
      <Box sx={{ flex: 1 }}>
        <Typography variant="subtitle1" fontWeight={700}>
          Check paused extraction
        </Typography>
        {reason ? (
          <Typography variant="caption" color="text.secondary">
            {reasonLabel(reason)}
          </Typography>
        ) : null}
      </Box>
      {loaded && scorePercent > 0 ? (
        <Tooltip title="Document quality score -- how well-formed the letter was for extraction">
          <Box
            sx={{
              mr: 2,
              px: 1.5,
              py: 0.5,
              bgcolor: `${scoreColor}18`,
              border: `1px solid ${scoreColor}`,
              borderRadius: "6px",
            }}
          >
            <Typography variant="caption" fontWeight={700} sx={{ color: scoreColor }}>
              Quality {scorePercent}%
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
  onAddSelection,
}: {
  sourceText: string;
  marks: ReturnType<typeof letterHighlightMarks>;
  onAddSelection: () => void;
}) {
  return (
    <Box
      sx={{
        width: { xs: "100%", md: "42%" },
        minWidth: 280,
        borderRight: "1px solid",
        borderColor: "divider",
        display: "flex",
        flexDirection: "column",
        bgcolor: "#FAFAFA",
        minHeight: 0,
      }}
    >
      <Box
        sx={{
          px: 2,
          py: 0.75,
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "#EFF6FF",
        }}
      >
        <Typography variant="caption" fontWeight={700} color="#1E40AF">
          Select any text on the letter to add it as a fact
        </Typography>
      </Box>
      <Box
        sx={{ flex: 1, overflow: "auto", p: 2, cursor: "text" }}
        onMouseUp={onAddSelection}
        data-testid="extraction-quality-letter"
      >
        <LetterMarkLegend marks={marks} />
        <LetterMarkdownView
          text={sourceText}
          marks={marks}
          emptyLabel="No letter text available for this task."
        />
      </Box>
    </Box>
  );
}

// -- ReviewFactsPane --------------------------------------------------------

function ReviewFactsPane({
  entities,
  quality,
  error,
  busy,
  onRemove,
  onPatch,
  onBack,
  onUnlock,
}: {
  entities: DraftEntity[];
  quality?: DocumentQuality;
  error: string;
  busy: boolean;
  onRemove: (text: string) => void;
  onPatch: (text: string, patch: Partial<DraftEntity>) => void;
  onBack: () => void;
  onUnlock: () => void;
}) {
  return (
    <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      <QualityBanner quality={quality} />
      {error ? (
        <Box
          sx={{
            px: 2,
            py: 1,
            bgcolor: "#FEF2F2",
            borderBottom: "1px solid",
            borderColor: "#FECACA",
            flexShrink: 0,
          }}
        >
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        </Box>
      ) : null}
      <Box sx={{ flex: 1, overflow: "auto", p: 2 }}>
        <FactList entities={entities} onRemove={onRemove} onPatch={onPatch} />
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

// -- QualityBanner ----------------------------------------------------------

function QualityBanner({ quality }: { quality?: DocumentQuality }) {
  const reasons = quality?.quality_reasons ?? [];
  if (!reasons.length) return null;
  return (
    <Stack
      direction="row"
      spacing={1}
      sx={{
        px: 2,
        py: 1.25,
        borderBottom: "1px solid",
        borderColor: "divider",
        bgcolor: "#FFFBEB",
        flexShrink: 0,
      }}
    >
      <WarningAmberIcon sx={{ color: "#D97706", fontSize: 18, mt: 0.15, flexShrink: 0 }} />
      <Box>
        <Typography variant="caption" fontWeight={700} color="#92400E">
          Why this referral paused
        </Typography>
        <Box component="ul" sx={{ m: 0, pl: 2 }}>
          {reasons.map((r) => (
            <Typography key={r} component="li" variant="caption" color="#78350F">
              {r.replace(/_/g, " ")}
            </Typography>
          ))}
        </Box>
      </Box>
    </Stack>
  );
}

// -- FactList ---------------------------------------------------------------

function FactList({
  entities,
  onRemove,
  onPatch,
}: {
  entities: DraftEntity[];
  onRemove: (text: string) => void;
  onPatch: (text: string, patch: Partial<DraftEntity>) => void;
}) {
  return (
    <>
      <Stack direction="row" alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="subtitle2" fontWeight={700} sx={{ flex: 1 }}>
          Draft facts
        </Typography>
        <Chip
          label={entities.length}
          size="small"
          sx={{ bgcolor: "#EFF6FF", color: "#1E40AF", fontWeight: 700 }}
        />
      </Stack>
      {entities.length === 0 ? (
        <Box
          sx={{
            border: "2px dashed",
            borderColor: "divider",
            borderRadius: "8px",
            p: 3,
            textAlign: "center",
          }}
        >
          <Typography variant="body2" color="text.secondary">
            No facts yet. Select text on the letter to add the key clinical facts.
          </Typography>
        </Box>
      ) : (
        <Stack spacing={0.75}>
          {entities.map((entity) => (
            <FactRow
              key={entity.text}
              entity={entity}
              onRemove={() => onRemove(entity.text)}
              onPatch={(patch) => onPatch(entity.text, patch)}
            />
          ))}
        </Stack>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
        Fix any wrong tags, then click Approve and unlock. The pipeline will continue from where it paused.
      </Typography>
    </>
  );
}

// -- FactRow ----------------------------------------------------------------

function FactRow({
  entity,
  onRemove,
  onPatch,
}: {
  entity: DraftEntity;
  onRemove: () => void;
  onPatch: (patch: Partial<DraftEntity>) => void;
}) {
  const bg = markBackground(entity.assertion, entity.semantic_tag);
  const fg = markForeground(entity.assertion, entity.semantic_tag);
  const bar = markContextBar(entity.assertion);
  const tagLabel = semanticTagLabel(entity.semantic_tag) || "Unset";
  const assertText = assertionLabel(entity.assertion) || "Present";

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "6px",
        overflow: "hidden",
        bgcolor: "#FFFFFF",
        transition: "border-color 0.15s",
        "&:hover": { borderColor: "primary.main" },
      }}
      data-testid="extraction-quality-fact-row"
    >
      <Tooltip title={assertText} placement="left">
        <Box
          sx={{
            width: 8,
            alignSelf: "stretch",
            bgcolor: bar,
            flexShrink: 0,
            cursor: "default",
          }}
        />
      </Tooltip>
      <Tooltip title="Semantic tag">
        <Box
          sx={{
            bgcolor: bg,
            color: fg,
            px: 0.75,
            py: 0.15,
            fontSize: "0.7rem",
            fontWeight: 700,
            flexShrink: 0,
            mx: 0.75,
            borderRadius: "3px",
          }}
        >
          {tagLabel}
        </Box>
      </Tooltip>
      <Typography
        variant="body2"
        sx={{
          flex: 1,
          fontWeight: 500,
          minWidth: 0,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={entity.text}
      >
        {entity.text}
      </Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mr: 0.5 }}>
        <FactSelect
          value={entity.semantic_tag ?? ""}
          label={`Semantic tag for ${entity.text}`}
          onChange={(v) => onPatch({ semantic_tag: v })}
        >
          <option value="">-- tag --</option>
          {TAG_OPTIONS.map((tag) => (
            <option key={tag} value={tag}>
              {tag.replace(/_/g, " ")}
            </option>
          ))}
        </FactSelect>
        <FactSelect
          value={entity.assertion ?? "present"}
          label={`Assertion for ${entity.text}`}
          onChange={(v) => onPatch({ assertion: v })}
        >
          {ASSERTION_OPTIONS.map(([val, lbl]) => (
            <option key={val} value={val}>
              {lbl}
            </option>
          ))}
        </FactSelect>
        <Tooltip title="Remove this fact">
          <IconButton
            size="small"
            onClick={onRemove}
            aria-label={`Remove ${entity.text}`}
          >
            <DeleteIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      </Box>
    </Box>
  );
}

// -- FactSelect -------------------------------------------------------------

function FactSelect({
  value,
  label,
  onChange,
  children,
}: {
  value: string;
  label: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <Box
      component="select"
      value={value}
      onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
      aria-label={label}
      sx={{
        fontSize: "0.72rem",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "4px",
        px: 0.5,
        py: 0.25,
        bgcolor: "transparent",
        cursor: "pointer",
        "&:focus": { outline: "2px solid", outlineColor: "primary.main" },
      }}
    >
      {children}
    </Box>
  );
}
