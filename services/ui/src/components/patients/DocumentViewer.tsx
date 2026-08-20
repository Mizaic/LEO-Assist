/**
 * DocumentViewer -- right-pane clinical document reader.
 *
 * Renders text inline, embeds PDFs, and opens reprocess chunk selection in a dialog.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
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
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import ReplayOutlinedIcon from "@mui/icons-material/ReplayOutlined";
import { patientDocumentFileUrl, type DocumentRow } from "@/lib/patientEprApi";
import MarkdownEditor from "@/components/markdown-editor/MarkdownEditor";
import ConfirmDialog from "@/components/ConfirmDialog";
import { deletePatientDocument } from "@/lib/patientDocumentsApi";
import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import { useOrg } from "@/context/OrgContext";
import {
  categoryLabel,
  extractSourceFilename,
  fileKindLabel,
  hasLinkedSbarAssessment,
  inferFileKind,
  isHtmlDocumentRow,
  isSbarDocument,
  isWordDocumentRow,
  looksLikeHtmlBody,
  stripDocumentHeader,
} from "./documentFormat";
import { DocumentChunkPanel } from "./DocumentChunkPanel";
import { DocumentAiReadyChip } from "./DocumentAiReadyChip";
import { DocumentEditorDialog } from "./DocumentEditorDialog";
import { DocumentHtmlPreviewPane } from "./DocumentHtmlPreviewPane";
import { DocumentWordPreviewPane } from "./DocumentWordPreviewPane";

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

function InlinePdfPane({ url, title }: { url: string; title: string }) {
  return (
    <Box
      component="iframe"
      src={url}
      title={title}
      data-testid="document-inline-pdf"
      sx={{
        display: "block",
        width: "100%",
        minHeight: 480,
        height: "calc(100vh - 320px)",
        border: "1px solid #E2E8F0",
        borderRadius: "8px",
        bgcolor: "#F8FAFC",
      }}
    />
  );
}

interface Props {
  doc: DocumentRow;
  patientId?: string;
  canManageDocuments?: boolean;
  onDocumentsChanged?: () => void;
}

function isEditableDocument(doc: DocumentRow): boolean {
  if (isSbarDocument(doc)) return false;
  return !doc.original_url && !doc.markdown_url;
}

export function DocumentViewer({
  doc,
  patientId,
  canManageDocuments = false,
  onDocumentsChanged,
}: Props) {
  const { isPlatformAdmin } = useOrg();
  const [viewMode, setViewMode] = useState<ViewMode>("rendered");
  const [editorOpen, setEditorOpen] = useState(false);
  const [reprocessOpen, setReprocessOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const kind = inferFileKind(doc);
  const sourceFile = extractSourceFilename(doc.full_text);
  const isSbar = isSbarDocument(doc);
  const linkedSbar = hasLinkedSbarAssessment(doc);
  const assessmentId = doc.sbar?.sbar_id?.trim() || "";
  const showSbarWidget = Boolean(assessmentId && (linkedSbar || isSbar));
  const sbarMd = buildSbarMarkdown(doc);
  const body = useMemo(
    () => stripDocumentHeader(doc.full_text || doc.text_preview || ""),
    [doc.full_text, doc.text_preview],
  );
  const showDocumentBody = Boolean(body) && !(isSbar && assessmentId);
  const openUrl = doc.original_url || doc.markdown_url;
  const showInlinePdf = kind === "pdf" && Boolean(openUrl);
  const showInlineWord = isWordDocumentRow(doc) && Boolean(openUrl);
  const showInlineHtml =
    isHtmlDocumentRow(doc) && Boolean(openUrl || looksLikeHtmlBody(body));
  const inlineFileUrl =
    patientId && showInlinePdf
      ? patientDocumentFileUrl(patientId, doc.document_id)
      : null;
  const showWordPreview = Boolean(patientId && showInlineWord);
  const showHtmlPreview = Boolean(patientId && showInlineHtml);
  const showManageActions = canManageDocuments && patientId && isEditableDocument(doc);
  const showReprocess = Boolean(isPlatformAdmin && patientId && !isSbar);

  const handleDelete = async () => {
    if (!patientId) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await deletePatientDocument(patientId, doc.document_id);
      setConfirmDelete(false);
      onDocumentsChanged?.();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Unable to delete document.");
    } finally {
      setDeleteBusy(false);
    }
  };

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
        {showReprocess && (
          <Button
            size="small"
            variant="outlined"
            startIcon={<ReplayOutlinedIcon />}
            onClick={() => setReprocessOpen(true)}
            data-testid="document-reprocess-button"
          >
            Reprocess
          </Button>
        )}
        {openUrl && (
          <Button
            size="small"
            variant="text"
            startIcon={<OpenInNewIcon />}
            href={openUrl}
            target="_blank"
            rel="noopener noreferrer"
            component="a"
          >
            Open in new tab
          </Button>
        )}
        {showManageActions && (
          <>
            <Button
              size="small"
              variant="outlined"
              startIcon={<EditOutlinedIcon />}
              onClick={() => setEditorOpen(true)}
              data-testid="edit-document-button"
            >
              Edit
            </Button>
            <Button
              size="small"
              color="error"
              variant="outlined"
              startIcon={<DeleteOutlineIcon />}
              onClick={() => setConfirmDelete(true)}
              data-testid="delete-document-button"
            >
              Delete
            </Button>
          </>
        )}
      </Stack>

      {deleteError && (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {deleteError}
        </Alert>
      )}

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
        <DocumentAiReadyChip chunkCount={doc.chunk_count ?? 0} size="medium" />
      </Stack>

      {isSbar && (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="document-sbar-reprocess-hint">
          To reprocess source chunks, select the referral Word or PDF document
          (for example BR7 updated 4.docx) in the list on the left.
        </Alert>
      )}

      {showSbarWidget && (
        <Box sx={{ mb: 2 }} data-testid={isSbar ? "document-sbar-widget" : "document-linked-sbar"}>
          {!isSbar && (
            <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ display: "block", mb: 1 }}>
              Linked SBAR assessment
            </Typography>
          )}
          <LeoSbarHost assessmentId={assessmentId} testId="document-sbar" />
        </Box>
      )}

      {!showSbarWidget && isSbar && sbarMd ? (
        <Alert severity="warning" data-testid="document-sbar-missing-id">
          This SBAR document is missing an assessment id. Open it from an
          Assessment row so the CDN widget can load the clinical summary.
        </Alert>
      ) : inlineFileUrl ? (
        <InlinePdfPane url={inlineFileUrl} title={doc.title} />
      ) : showWordPreview && patientId ? (
        <DocumentWordPreviewPane patientId={patientId} documentId={doc.document_id} />
      ) : showHtmlPreview && patientId ? (
        <DocumentHtmlPreviewPane
          patientId={patientId}
          documentId={doc.document_id}
          inlineHtml={looksLikeHtmlBody(body) ? body : undefined}
          title={doc.title}
        />
      ) : showDocumentBody ? (
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
            ? `This ${fileKindLabel(kind).toLowerCase()} file could not be embedded. Use Open in new tab.`
            : "No readable content is available for this document yet."}
        </Alert>
      )}

      {showReprocess && patientId && (
        <DocumentChunkPanel
          patientId={patientId}
          doc={doc}
          open={reprocessOpen}
          onClose={() => setReprocessOpen(false)}
        />
      )}

      {showManageActions && patientId && (
        <>
          <DocumentEditorDialog
            open={editorOpen}
            patientId={patientId}
            initial={{
              documentId: doc.document_id,
              title: doc.title,
              category: doc.category ?? "referral",
              documentDate: doc.document_date?.slice(0, 10) ?? "",
              markdownBody: doc.full_text || doc.text_preview || "",
              episodeId: doc.episode_id ?? "",
            }}
            onClose={() => setEditorOpen(false)}
            onSaved={() => onDocumentsChanged?.()}
          />
          {confirmDelete && (
            <ConfirmDialog
              title="Delete document?"
              body={`This will permanently delete ${doc.title}. This cannot be undone.`}
              confirmLabel="Delete"
              variant="danger"
              busy={deleteBusy}
              busyLabel="Deleting..."
              onConfirm={() => void handleDelete()}
              onCancel={() => setConfirmDelete(false)}
            />
          )}
        </>
      )}
    </Box>
  );
}
