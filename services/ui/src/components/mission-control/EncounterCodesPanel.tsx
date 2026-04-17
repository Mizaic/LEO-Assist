"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { CodedLink } from "@/lib/types";
import {
  DEFAULT_TAG_STYLE,
  getLinkAssertion,
  getTagStyle,
  isNegatedOrAbsent,
  type TagStyle,
} from "./encounterStyles";
import { deriveEvidenceSentence } from "./encounterTextUtils";

export interface CodesPanelEncounter {
  encounter_id: string;
  text: string | null;
  coded_count: number;
}

interface CodesPanelProps {
  enc: CodesPanelEncounter;
  codingLoading: boolean;
  codingLinks: CodedLink[];
  codingError: string | undefined;
}

// Tag filter pills shown above the chip list. When 2+ distinct types
// exist, pills become clickable toggles.
function TagLegend({
  links,
  activeTagLabels,
  onToggle,
  onClear,
}: {
  links: CodedLink[];
  activeTagLabels: Set<string>;
  onToggle: (label: string) => void;
  onClear: () => void;
}) {
  const seen = new Map<string, TagStyle>();
  for (const link of links) {
    const style = getTagStyle(link.semantic_tag);
    if (!seen.has(style.label)) seen.set(style.label, style);
  }
  if (seen.size < 2) return null;

  const hasFilter = activeTagLabels.size > 0;

  return (
    <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mb: 0.75, alignItems: "center" }}>
      {Array.from(seen.entries()).map(([label, style]) => {
        const isActive = activeTagLabels.has(label);
        const isDimmed = hasFilter && !isActive;
        return (
          <Box
            key={label}
            role="button"
            tabIndex={0}
            aria-pressed={isActive}
            aria-label={`Filter by ${label}`}
            onClick={() => onToggle(label)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") onToggle(label);
            }}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 0.4,
              px: 0.75,
              py: 0.25,
              borderRadius: "4px",
              border: "1px solid",
              borderColor: isDimmed ? "#e2e8f0" : style.borderColor,
              bgcolor: isActive ? style.borderColor : isDimmed ? "#f8fafc" : style.bgcolor,
              cursor: "pointer",
              opacity: isDimmed ? 0.55 : 1,
              transition: "all 0.12s ease",
              userSelect: "none",
              outline: "none",
              "&:hover": { opacity: 1, borderColor: style.borderColor },
              "&:focus-visible": { outline: `2px solid ${style.borderColor}`, outlineOffset: 1 },
            }}
          >
            <Box
              sx={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                bgcolor: isActive ? "white" : style.borderColor,
                flexShrink: 0,
              }}
            />
            <Typography
              variant="caption"
              sx={{
                fontSize: "0.68rem",
                color: isActive ? "white" : isDimmed ? "#94a3b8" : style.color,
                lineHeight: 1,
              }}
            >
              {label}
            </Typography>
          </Box>
        );
      })}
      {hasFilter && (
        <Box
          role="button"
          tabIndex={0}
          aria-label="Clear type filter"
          onClick={onClear}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onClear(); }}
          sx={{
            px: 0.75,
            py: 0.25,
            borderRadius: "4px",
            border: "1px solid #e2e8f0",
            bgcolor: "transparent",
            cursor: "pointer",
            userSelect: "none",
            outline: "none",
            "&:hover": { borderColor: "#94a3b8" },
            "&:focus-visible": { outline: "2px solid #94a3b8", outlineOffset: 1 },
          }}
        >
          <Typography variant="caption" sx={{ fontSize: "0.68rem", color: "#64748b", lineHeight: 1 }}>
            Clear filter
          </Typography>
        </Box>
      )}
    </Box>
  );
}

function CodeChips({
  enc,
  links,
}: {
  enc: CodesPanelEncounter;
  links: CodedLink[];
}) {
  return (
    <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
      {links.map((link, linkIndex) => {
        const style = getTagStyle(link.semantic_tag) ?? DEFAULT_TAG_STYLE;
        const sentenceEvidence =
          link.evidence_sentence ?? deriveEvidenceSentence(enc.text, link.evidence);
        const tooltipRows = [
          `Coded term: ${link.term || "Unknown term"}`,
          `Concept ID: ${link.concept_id}`,
        ];
        if (link.semantic_tag) tooltipRows.push(`Type: ${link.semantic_tag}`);
        const assertion = getLinkAssertion(link);
        if (assertion) tooltipRows.push(`Assertion: ${assertion}`);
        if (sentenceEvidence) tooltipRows.push(`Sentence: ${sentenceEvidence}`);
        if (link.evidence) tooltipRows.push(`Mention: ${link.evidence}`);
        if (
          typeof link.evidence_start === "number" &&
          typeof link.evidence_end === "number"
        ) {
          tooltipRows.push(`Mention offsets: ${link.evidence_start}-${link.evidence_end}`);
        }
        if (typeof link.sentence_index === "number") {
          tooltipRows.push(`Sentence index: ${link.sentence_index}`);
        }
        const negatedOrAbsent = isNegatedOrAbsent(link);
        return (
          <Tooltip
            key={`${enc.encounter_id}-${link.concept_id}-${link.sentence_index ?? "na"}-${linkIndex}`}
            placement="top"
            title={
              <Box sx={{ whiteSpace: "pre-wrap", fontSize: "0.75rem" }}>
                {tooltipRows.join("\n")}
              </Box>
            }
          >
            <Chip
              size="small"
              variant="outlined"
              label={`${link.term || "Unknown term"} (${link.concept_id})`}
              sx={{
                borderColor: negatedOrAbsent ? "#dc2626" : style.borderColor,
                borderWidth: negatedOrAbsent ? 1.25 : 1,
                bgcolor: style.bgcolor,
                color: style.color,
                "& .MuiChip-label": { color: style.color },
              }}
            />
          </Tooltip>
        );
      })}
    </Box>
  );
}

export default function CodesPanel({
  enc,
  codingLoading,
  codingLinks,
  codingError,
}: CodesPanelProps) {
  const [activeTagLabels, setActiveTagLabels] = useState<Set<string>>(new Set());

  const toggleTag = (label: string) =>
    setActiveTagLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });

  const clearFilter = () => setActiveTagLabels(new Set());

  const hasCodes = (enc.coded_count ?? 0) > 0;
  if (!hasCodes && !codingLoading && !codingError) return null;

  const filteredLinks =
    activeTagLabels.size === 0
      ? codingLinks
      : codingLinks.filter((l) => activeTagLabels.has(getTagStyle(l.semantic_tag).label));

  return (
    <Box sx={{ mb: 1, px: 0.5 }}>
      {codingLoading && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.5 }}>
          <CircularProgress size={14} aria-label="Loading coded concepts" />
          <Typography variant="caption" color="text.secondary">
            Loading coded concepts...
          </Typography>
        </Box>
      )}
      {!codingLoading && codingError && (
        <Alert severity="error" sx={{ py: 0 }}>
          {codingError}
        </Alert>
      )}
      {!codingLoading && !codingError && codingLinks.length === 0 && hasCodes && (
        <Typography variant="caption" color="text.secondary">
          {enc.coded_count} coded {enc.coded_count === 1 ? "concept" : "concepts"} -- loading...
        </Typography>
      )}
      {!codingLoading && !codingError && codingLinks.length > 0 && (
        <>
          <TagLegend
            links={codingLinks}
            activeTagLabels={activeTagLabels}
            onToggle={toggleTag}
            onClear={clearFilter}
          />
          <CodeChips enc={enc} links={filteredLinks} />
          {activeTagLabels.size > 0 && filteredLinks.length < codingLinks.length && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              Showing {filteredLinks.length} of {codingLinks.length} coded concepts
            </Typography>
          )}
        </>
      )}
    </Box>
  );
}
