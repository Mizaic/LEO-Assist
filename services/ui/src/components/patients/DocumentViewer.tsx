/**
 * DocumentViewer -- right-pane clinical document reader.
 *
 * Renders chunk text as markdown, with raw toggle and open-original link
 * when a PDF or Word file URL is available.
 */
"use client";

import { useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import type { DocumentRow } from "@/lib/patientEprApi";
import MarkdownEditor from "@/components/markdown-editor/MarkdownEditor";
import { SbarFinalView } from "@/components/sbar-final/SbarFinalView";
import {
  categoryLabel,
  extractSourceFilename,
  fileKindLabel,
  inferFileKind,
} from "./documentFormat";

type ViewMode = "rendered" | "raw";

function fmt(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function buildSbarMarkdown(doc: DocumentRow): string {
  const s = doc.sbar;
  if (!s) return "";
  const parts: string[] = [];
  if (s.situation) parts.push(`## Situation\n\n${s.situation}`);
  if (s.background) parts.push(`## Background\n\n${s.background}`);
  if (s.assessment) parts.push(`## Assessment\n\n${s.assessment}`);
  if (s.recommendation) parts.push(`## Recommendation\n\n${s.recommendation}`);
  return parts.join("\n\n");
}

const DOC_HEADER_RE = /^--- Document:\s*.+?\s*---\s*\n?/m;

function stripDocHeader(text: string): string {
  return text.replace(DOC_HEADER_RE, "").trim();
}

function RawPane({ body }: { body: string }) {
  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 0,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        fontSize: "0.82rem",
        lineHeight: 1.65,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {body}
    </Box>
  );
}

function RenderedPane({ body }: { body: string }) {
  return (
    <Box
      sx={{
        "& .md-editor": { border: "none", borderRadius: 0 },
        "& .md-editor .tiptap": { minHeight: 0 },
      }}
    >
      <MarkdownEditor
        key={body.slice(0, 80)}
        initialContent={body}
        mode="view"
        minHeight={0}
        className="epr-document-markdown"
      />
    </Box>
  );
}

interface Props {
  doc: DocumentRow;
}

export function DocumentViewer({ doc }: Props) {
  const [viewMode, setViewMode] = useState<ViewMode>("rendered");
  const kind = inferFileKind(doc);
  const sourceFile = extractSourceFilename(doc.full_text);
  const isSbar = doc.document_type.toLowerCase().includes("sbar") || Boolean(doc.sbar);
  const sbarMd = buildSbarMarkdown(doc);
  const body = useMemo(
    () => stripDocHeader(doc.full_text || doc.text_preview || ""),
    [doc.full_text, doc.text_preview]
  );
  const openUrl = doc.original_url || doc.markdown_url;

  return (
    <Box sx={{ p: 2, height: "100%", overflowY: "auto" }}>
      <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" sx={{ mb: 1.5 }}>
        <Box sx={{ flex: 1, minWidth: 200 }}>
          <Typography variant="subtitle2" fontWeight={700} component="h2">
            {doc.title}
          </Typography>
          {sourceFile && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              Source file: {sourceFile}
            </Typography>
          )}
        </Box>
        {openUrl && (
          <Button
            size="small"
            variant="outlined"
            startIcon={<OpenInNewIcon />}
            href={openUrl}
            target="_blank"
            rel="noopener noreferrer"
            component="a"
          >
            Open {fileKindLabel(kind)}
          </Button>
        )}
      </Stack>

      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" sx={{ mb: 2 }}>
        <Chip label={fileKindLabel(kind)} size="small" sx={{ height: 20, fontSize: 10 }} />
        <Chip label={doc.document_type} size="small" sx={{ height: 20, fontSize: 10 }} />
        {doc.category && (
          <Chip
            label={categoryLabel(doc.category)}
            size="small"
            sx={{ height: 20, fontSize: 10, bgcolor: "#F1F5F9" }}
          />
        )}
        {doc.document_date && (
          <Typography variant="caption" color="text.secondary">
            {fmt(doc.document_date)}
          </Typography>
        )}
      </Stack>

      {isSbar && sbarMd ? (
        <SbarFinalView markdown={sbarMd} testOnly={false} />
      ) : body ? (
        <>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: 1.5 }}
          >
            <Typography variant="caption" fontWeight={700} color="text.secondary">
              Document content
            </Typography>
            <ToggleButtonGroup
              exclusive
              size="small"
              value={viewMode}
              onChange={(_, next: ViewMode | null) => {
                if (next) setViewMode(next);
              }}
              aria-label="Document view mode"
            >
              <ToggleButton value="rendered">Rendered</ToggleButton>
              <ToggleButton value="raw">Raw</ToggleButton>
            </ToggleButtonGroup>
          </Stack>
          {viewMode === "rendered" ? <RenderedPane body={body} /> : <RawPane body={body} />}
        </>
      ) : (
        <Alert severity="info">
          {openUrl
            ? "This document is stored as a file. Use Open to view the original."
            : "No readable content is available for this document yet."}
        </Alert>
      )}
    </Box>
  );
}
