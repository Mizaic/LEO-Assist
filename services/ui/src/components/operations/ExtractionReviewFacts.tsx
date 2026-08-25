/**
 * Draft fact list for extraction quality review.
 *
 * Atlas trace: DI-4A012A59 / DO-E7824FED
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";
import {
  assertionLabel,
  markBackground,
  markContextBar,
  markForeground,
  semanticTagLabel,
  TAG_STYLE,
} from "@/app/admin/validation-lab/letterMarkStyle";
import ExtractionReviewAskLeo from "./ExtractionReviewAskLeo";
import { countMentions, mentionCopy } from "./extractionReviewHighlight";

export interface DraftEntity {
  text: string;
  semantic_tag?: string;
  assertion?: string;
  source?: string;
  __source?: string;
}

export function draftExtractor(entity: DraftEntity): string {
  return String(entity.source || entity.__source || "").trim();
}

export interface DocumentQuality {
  document_quality_score?: number;
  quality_reasons?: string[];
}

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

export function FactList({
  entities,
  letterText,
  pickedText,
  onPick,
  onRemove,
  onPatch,
}: {
  entities: DraftEntity[];
  letterText: string;
  pickedText: string;
  onPick: (text: string) => void;
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
          sx={{ bgcolor: "action.hover", color: "primary.main", fontWeight: 700 }}
        />
      </Stack>
      {pickedText ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          {mentionCopy(pickedText, countMentions(letterText, pickedText))}
        </Typography>
      ) : null}
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
            <Box key={entity.text}>
              <FactRow
                entity={entity}
                selected={entity.text === pickedText}
                mentionCount={countMentions(letterText, entity.text)}
                onPick={() => onPick(entity.text)}
                onRemove={() => onRemove(entity.text)}
                onPatch={(patch) => onPatch(entity.text, patch)}
              />
              {entity.text === pickedText ? (
                <ExtractionReviewAskLeo
                  entityText={entity.text}
                  letterText={letterText}
                  assertion={entity.assertion ?? "present"}
                  onApply={(patch) => onPatch(entity.text, patch)}
                />
              ) : null}
            </Box>
          ))}
        </Stack>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
        Click a fact to number each mention on the letter. Ask LEO if the tag
        is unclear. Then click Approve and unlock.
      </Typography>
    </>
  );
}

function FactRow({
  entity,
  selected,
  mentionCount,
  onPick,
  onRemove,
  onPatch,
}: {
  entity: DraftEntity;
  selected: boolean;
  mentionCount: number;
  onPick: () => void;
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
      role="button"
      tabIndex={0}
      onClick={onPick}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onPick();
        }
      }}
      sx={{
        display: "flex",
        alignItems: "center",
        border: "1px solid",
        borderColor: selected ? "primary.main" : "divider",
        borderRadius: "6px",
        overflow: "hidden",
        bgcolor: "background.paper",
        cursor: "pointer",
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
      {selected ? (
        <Box
          sx={{ display: "flex", alignItems: "center", gap: 0.5, mr: 0.5 }}
          onClick={(event) => event.stopPropagation()}
        >
          <FactSelect
            value={entity.semantic_tag ?? ""}
            label={`Semantic tag for ${entity.text}`}
            onChange={(value) => onPatch({ semantic_tag: value })}
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
            onChange={(value) => onPatch({ assertion: value })}
          >
            {ASSERTION_OPTIONS.map(([val, lbl]) => (
              <option key={val} value={val}>
                {lbl}
              </option>
            ))}
          </FactSelect>
          <Tooltip title="Remove this fact">
            <IconButton size="small" onClick={onRemove} aria-label={`Remove ${entity.text}`}>
              <DeleteIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        </Box>
      ) : (
        <Typography variant="caption" color="text.secondary" sx={{ mr: 1, flexShrink: 0 }}>
          {assertText}
          {mentionCount ? ` · ${mentionCount}` : ""}
        </Typography>
      )}
    </Box>
  );
}

function FactSelect({
  value,
  label,
  onChange,
  children,
}: {
  value: string;
  label: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <Box
      component="select"
      value={value}
      onChange={(event: React.ChangeEvent<HTMLSelectElement>) => onChange(event.target.value)}
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
